import os
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
from .fio_client import FIOClient, build_production_map

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


def format_price(listing) -> str:
    """Format a listing's price for display."""
    if listing.price_type == PriceType.ABSOLUTE:
        return f"{listing.price_value:,.0f}/u" if listing.price_value else "Contact me"
    elif listing.price_type == PriceType.CX_RELATIVE:
        if listing.price_value is None:
            return "CX price"
        sign = "+" if listing.price_value >= 0 else ""
        exchange = f".{listing.price_exchange}" if listing.price_exchange else ""
        return f"CX{exchange}{sign}{listing.price_value:.0f}%"
    else:
        return "Contact me"


# Add helper to Jinja2 globals
templates.env.globals["format_price"] = format_price

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(listings.router, prefix="/listings", tags=["listings"])
app.include_router(profile.router, prefix="/u", tags=["profile"])


@app.get("/")
async def home(request: Request):
    """Home page."""
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "title": "PrUnderground"},
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

    # Fetch production suggestions from FIO
    suggestions = []
    if user.fio_api_key:
        client = FIOClient(api_key=user.fio_api_key)
        try:
            buildings = await client.get_user_planet_buildings(user.fio_username)
            recipes = await client.get_building_recipes()
            production_map = build_production_map(buildings, recipes)
            suggestions = sorted(production_map.keys())
        except Exception:
            pass
        finally:
            await client.close()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "current_user": user,
            "listings": user_listings,
            "suggestions": suggestions,
            "format_price": format_price,
        },
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
