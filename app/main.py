import os
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import engine, Base, get_db
from .models import User, Listing, PriceType
from .routers import auth, listings, profile
from .routers.auth import get_current_user, require_user
from .fio_client import FIOClient, extract_active_production, extract_storage_locations
from .utils import format_price

# Create database tables
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="PrUnderground",
    description="Community trade coordination for Prosperous Universe",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Set up templates
templates = Jinja2Templates(directory="app/templates")


# Add helper to Jinja2 globals
templates.env.globals["format_price"] = format_price

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


@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """User dashboard."""
    user = require_user(request, db)

    # Get user's listings
    user_listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
        .order_by(Listing.updated_at.desc())
        .all()
    )

    # Fetch what user is actually producing from FIO
    suggestions = []
    storage_inventory = {}  # Map storage_id -> {material_ticker -> amount}
    if user.fio_api_key:
        client = FIOClient(api_key=user.fio_api_key)
        try:
            production_lines = await client.get_user_production(user.fio_username)
            active_materials = extract_active_production(production_lines)
            suggestions = sorted(active_materials)

            # Fetch storage data for live inventory
            raw_storages = await client.get_user_storage(user.fio_username)
            sites = await client.get_user_sites(user.fio_username)
            warehouses = await client.get_user_warehouses(user.fio_username)
            storages = extract_storage_locations(raw_storages, sites, warehouses)

            # Build inventory map for quick lookup
            for storage in storages:
                storage_inventory[storage["addressable_id"]] = storage["items"]
        except Exception as e:
            print(f"DEBUG: FIO error: {e}")
        finally:
            await client.close()

    # Compute available quantity for each listing with storage tracking
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

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "current_user": user,
            "listings": user_listings,
            "suggestions": suggestions,
            "format_price": format_price,
            "listing_inventory": listing_inventory,
            "now": datetime.utcnow(),
        },
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
