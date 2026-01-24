import logging
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .database import engine, Base, get_db
from .models import User, Listing
from .routers import auth, listings, profile
from .routers.auth import get_current_user, require_user
from .fio_client import FIOClient, extract_active_production, extract_storage_locations
from .fio_cache import fio_cache
from .utils import format_price
from .audit import AuditLog, log_audit, AuditAction  # Import to register model
from .template_utils import templates, render_template

# App version - single source of truth
__version__ = "1.0.0"

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
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="PrUnderground",
    description="Community trade coordination for Prosperous Universe",
    version=__version__,
    lifespan=lifespan,
)

# Make version available to all templates
templates.env.globals["app_version"] = __version__

# Attach rate limiter to app
app.state.limiter = limiter




# Custom rate limit exceeded handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return PlainTextResponse(
        content=f"Rate limit exceeded. Please try again later. Limit: {exc.detail}",
        status_code=429,
    )

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(listings.router, prefix="/listings", tags=["listings"])
app.include_router(profile.router, prefix="/u", tags=["profile"])


@app.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    """Home page."""
    current_user = get_current_user(request, db)
    return templates.TemplateResponse(
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
    """User dashboard - loads fast, FIO data fetched via HTMX."""
    user = require_user(request, db)

    # Get user's listings from DB (fast)
    user_listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
        .order_by(Listing.updated_at.desc())
        .all()
    )

    # Get cache status for display
    cache_status = fio_cache.get_cache_status(user.fio_username)

    return render_template(
        request,
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "current_user": user,
            "listings": user_listings,
            "format_price": format_price,
            "now": datetime.utcnow(),
            "cache_status": cache_status,
        },
    )


async def fetch_and_cache_fio_data(user: User, force_refresh: bool = False):
    """
    Fetch FIO data for a user, using cache unless force_refresh is True.
    Returns tuple of (suggestions, storage_locations, storage_inventory_map).
    """
    username = user.fio_username

    # Check cache first (unless forcing refresh)
    if not force_refresh:
        cached_suggestions = fio_cache.get_suggestions(username)
        cached_storage_locations = fio_cache.get_storage_locations(username)

        if cached_suggestions is not None and cached_storage_locations is not None:
            # Build inventory map from cached storage locations
            storage_inventory = {}
            for storage in cached_storage_locations:
                storage_inventory[storage["addressable_id"]] = storage["items"]
            return cached_suggestions, cached_storage_locations, storage_inventory

    # Need to fetch from FIO
    suggestions = []
    storage_locations = []
    storage_inventory = {}

    if user.fio_api_key:
        client = FIOClient(api_key=user.fio_api_key)
        try:
            # Fetch all data
            production_lines = await client.get_user_production(username)
            raw_storages = await client.get_user_storage(username)
            sites = await client.get_user_sites(username)
            warehouses = await client.get_user_warehouses(username)

            # Process data
            suggestions = sorted(extract_active_production(production_lines))
            storage_locations = extract_storage_locations(raw_storages, sites, warehouses)

            # Build inventory map
            for storage in storage_locations:
                storage_inventory[storage["addressable_id"]] = storage["items"]

            # Cache everything
            fio_cache.set_production(username, production_lines)
            fio_cache.set_storage(username, raw_storages)
            fio_cache.set_sites(username, sites)
            fio_cache.set_warehouses(username, warehouses)
            fio_cache.set_suggestions(username, suggestions)
            fio_cache.set_storage_locations(username, storage_locations)
            fio_cache.set_last_refresh(username)

        except Exception as e:
            logger.error(f"FIO fetch error for {username}: {e}")
        finally:
            await client.close()

    return suggestions, storage_locations, storage_inventory


@app.get("/api/dashboard/suggestions", response_class=HTMLResponse)
async def dashboard_suggestions(request: Request, db: Session = Depends(get_db)):
    """HTMX endpoint: Fetch production suggestions (cached)."""
    user = require_user(request, db)

    suggestions, _, _ = await fetch_and_cache_fio_data(user)

    return templates.TemplateResponse(
        "partials/dashboard_suggestions.html",
        {"request": request, "suggestions": suggestions},
    )


@app.get("/api/dashboard/inventory", response_class=HTMLResponse)
async def dashboard_inventory(request: Request, db: Session = Depends(get_db)):
    """HTMX endpoint: Fetch live inventory (cached)."""
    user = require_user(request, db)

    # Get user's listings from DB
    user_listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
        .order_by(Listing.updated_at.desc())
        .all()
    )

    _, _, storage_inventory = await fetch_and_cache_fio_data(user)

    # Compute available quantity for each listing
    listing_inventory = {}
    for listing in user_listings:
        if listing.storage_id and listing.storage_id in storage_inventory:
            items = storage_inventory[listing.storage_id]
            actual = items.get(listing.material_ticker, 0)
            reserve = listing.reserve_quantity or 0
            available = max(0, actual - reserve)
            listing_inventory[listing.id] = {
                "actual": actual,
                "reserve": reserve,
                "available": available,
            }

    return render_template(
        request,
        "partials/dashboard_inventory.html",
        {
            "request": request,
            "listings": user_listings,
            "listing_inventory": listing_inventory,
            "format_price": format_price,
            "now": datetime.utcnow(),
        },
    )


@app.post("/api/fio/refresh", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def refresh_fio_data(request: Request, db: Session = Depends(get_db)):
    """Force refresh FIO data from API, bypassing cache."""
    user = require_user(request, db)

    # Invalidate cache and fetch fresh
    fio_cache.invalidate_user(user.fio_username)
    await fetch_and_cache_fio_data(user, force_refresh=True)

    # Audit log
    log_audit(db, AuditAction.FIO_REFRESH, user_id=user.id)

    # Return updated cache status
    cache_status = fio_cache.get_cache_status(user.fio_username)
    last_refresh = cache_status.get("last_refresh")

    return f'<span class="fio-refresh-status">Last updated: just now</span>'


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
