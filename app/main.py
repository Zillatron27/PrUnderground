import logging
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .database import engine, Base, get_db
from .models import User, Listing, Bundle
from .routers import auth, listings, profile, data, bundles, admin
from .routers.auth import get_current_user, require_user
from .fio_client import FIOClient, extract_active_production
from .fio_cache import fio_cache
from .encryption import decrypt_api_key
from .utils import format_price
from .audit import AuditLog, log_audit, AuditAction  # Import to register model
from .template_utils import templates, render_template
from .services.fio_sync import sync_user_fio_data, get_sync_staleness
from .services.material_sync import sync_materials, is_material_sync_needed, get_material_category_map
from .services.planet_sync import sync_planets, is_planet_sync_needed
from .services.cx_sync import get_cx_prices_bulk, get_sync_age_string as get_cx_sync_age
from .services.telemetry import increment_stat, Metrics
from .scheduler import start_scheduler, stop_scheduler

# App version - single source of truth
__version__ = "1.1.0"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: sync materials and planets if needed
    from .database import SessionLocal
    db = SessionLocal()
    try:
        if is_material_sync_needed(db):
            logger.info("Materials table empty or stale, syncing from FIO...")
            inserted, updated = await sync_materials(db, force=True)
            logger.info(f"Material sync complete: {inserted} new, {updated} updated")

        if is_planet_sync_needed(db):
            logger.info("Planets table empty or stale, syncing from FIO...")
            inserted, updated = await sync_planets(db, force=True)
            logger.info(f"Planet sync complete: {inserted} new, {updated} updated")
    except Exception as e:
        logger.error(f"Startup sync failed: {e}")
    finally:
        db.close()

    # Start background scheduler for CX price sync
    start_scheduler()

    yield

    # Shutdown: stop scheduler
    stop_scheduler()


app = FastAPI(
    title="PrUnderground",
    description="Community trade coordination for Prosperous Universe",
    version=__version__,
    lifespan=lifespan,
)

# Trust proxy headers from Cloudflare tunnel for correct HTTPS redirects
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

# Make version and helpers available to all templates
templates.env.globals["app_version"] = __version__
templates.env.globals["get_sync_staleness"] = get_sync_staleness

# Attach rate limiter to app
app.state.limiter = limiter




# Custom rate limit exceeded handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return PlainTextResponse(
        content=f"Rate limit exceeded. Please try again later. Limit: {exc.detail}",
        status_code=429,
    )


# Middleware to allow embedding in APEX (Refined PrUn's XIT WEB command)
@app.middleware("http")
async def frame_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' https://apex.prosperousuniverse.com "
        "https://www.prosperousuniverse.com"
    )
    return response

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(listings.router, prefix="/listings", tags=["listings"])
app.include_router(bundles.router, prefix="/bundles", tags=["bundles"])
app.include_router(profile.router, prefix="/u", tags=["profile"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(data.router)


@app.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    """Home page."""
    current_user = get_current_user(request, db)
    return render_template(
        request,
        "home.html",
        {"request": request, "title": "PrUnderground", "current_user": current_user},
    )


@app.get("/about")
async def about(request: Request, db: Session = Depends(get_db)):
    """About page."""
    current_user = get_current_user(request, db)
    return templates.TemplateResponse(
        "about.html",
        {"request": request, "title": "About", "current_user": current_user},
    )


@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """User dashboard - reads from DB, FIO sync triggered via HTMX."""
    user = require_user(request, db)

    # Get user's listings from DB (fast)
    user_listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
        .order_by(Listing.updated_at.desc())
        .all()
    )

    # Get user's bundles from DB
    user_bundles = (
        db.query(Bundle)
        .filter(Bundle.user_id == user.id)
        .order_by(Bundle.updated_at.desc())
        .all()
    )

    # Get CX prices for calculated price display
    cx_prices = get_cx_prices_bulk(db)
    cx_sync_age = get_cx_sync_age(db)

    # Get material category mapping for colored tickers
    material_categories = get_material_category_map(db)

    return render_template(
        request,
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "current_user": user,
            "listings": user_listings,
            "bundles": user_bundles,
            "format_price": format_price,
            "now": datetime.utcnow(),
            "cx_prices": cx_prices,
            "cx_sync_age": cx_sync_age,
            "material_categories": material_categories,
        },
    )


async def fetch_suggestions(user: User) -> list:
    """
    Fetch production suggestions for a user (what they're producing).
    Uses cache if available, fetches from FIO if not.
    """
    username = user.fio_username

    # Check cache first
    cached = fio_cache.get_suggestions(username)
    if cached is not None:
        return cached

    # Fetch from FIO
    suggestions = []
    if user.fio_api_key:
        decrypted_key = decrypt_api_key(user.fio_api_key)
        client = FIOClient(api_key=decrypted_key)
        try:
            production_lines = await client.get_user_production(username)
            suggestions = sorted(extract_active_production(production_lines))
            fio_cache.set_suggestions(username, suggestions)
        except Exception as e:
            logger.error(f"Failed to fetch suggestions for {username}: {e}")
        finally:
            await client.close()

    return suggestions


@app.get("/api/dashboard/suggestions", response_class=HTMLResponse)
async def dashboard_suggestions(request: Request, db: Session = Depends(get_db)):
    """HTMX endpoint: Fetch production suggestions (cached)."""
    user = require_user(request, db)
    suggestions = await fetch_suggestions(user)
    material_categories = get_material_category_map(db)

    return templates.TemplateResponse(
        "partials/dashboard_suggestions.html",
        {"request": request, "suggestions": suggestions, "material_categories": material_categories},
    )


@app.get("/api/dashboard/inventory", response_class=HTMLResponse)
async def dashboard_inventory(request: Request, db: Session = Depends(get_db)):
    """HTMX endpoint: Sync FIO data and return inventory table."""
    user = require_user(request, db)

    # Sync FIO data (updates available_quantity in DB)
    await sync_user_fio_data(user, db)

    # Re-fetch listings with updated data
    user_listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
        .order_by(Listing.updated_at.desc())
        .all()
    )

    # Build listing_inventory dict for template (actual/reserve/available breakdown)
    listing_inventory = {}
    for listing in user_listings:
        if listing.available_quantity is not None:
            reserve = listing.reserve_quantity or 0
            actual = listing.available_quantity + reserve
            listing_inventory[listing.id] = {
                "actual": actual,
                "reserve": reserve,
                "available": listing.available_quantity,
            }

    cx_prices = get_cx_prices_bulk(db)
    material_categories = get_material_category_map(db)

    return render_template(
        request,
        "partials/dashboard_inventory.html",
        {
            "request": request,
            "listings": user_listings,
            "listing_inventory": listing_inventory,
            "format_price": format_price,
            "now": datetime.utcnow(),
            "cx_prices": cx_prices,
            "material_categories": material_categories,
        },
    )


@app.get("/api/dashboard/status", response_class=HTMLResponse)
async def dashboard_status(request: Request, db: Session = Depends(get_db)):
    """HTMX endpoint: Get current FIO sync status."""
    user = require_user(request, db)
    staleness = get_sync_staleness(user)
    cx_sync_age = get_cx_sync_age(db)

    parts = []
    if user.fio_last_synced:
        parts.append(f'<span class="fio-refresh-status">FIO data: {staleness}</span>')
    else:
        parts.append('<span class="fio-refresh-status">FIO data not synced</span>')

    if cx_sync_age:
        parts.append(f'<span class="fio-refresh-status">CX prices: {cx_sync_age}</span>')

    return " · ".join(parts)


@app.post("/api/fio/refresh", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def refresh_fio_data(request: Request, db: Session = Depends(get_db)):
    """Force refresh FIO data from API."""
    user = require_user(request, db)

    # Sync FIO data (forced refresh)
    success = await sync_user_fio_data(user, db, force=True)

    # Audit log and telemetry
    log_audit(db, AuditAction.FIO_REFRESH, user_id=user.id)
    increment_stat(db, Metrics.FIO_SYNCS)

    # Also invalidate suggestions cache so they refresh
    fio_cache.invalidate_user(user.fio_username)

    if success:
        return '<span class="fio-refresh-status">FIO data updated: just now</span>'
    else:
        return '<span class="fio-refresh-status">Sync failed - check API key</span>'


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
