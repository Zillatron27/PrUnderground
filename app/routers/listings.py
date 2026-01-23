from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import User, Listing, PriceType, ListingType
from ..schemas import ListingCreate, ListingUpdate
from ..fio_client import FIOClient, build_production_map
from .auth import get_current_user, require_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def browse_listings(
    request: Request,
    material: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Browse all listings, optionally filtered."""
    query = db.query(Listing).join(User)

    if material:
        query = query.filter(Listing.material_ticker.ilike(f"%{material}%"))
    if location:
        query = query.filter(Listing.location.ilike(f"%{location}%"))

    listings = query.order_by(Listing.updated_at.desc()).all()
    current_user = get_current_user(request, db)

    return templates.TemplateResponse(
        "listings/browse.html",
        {
            "request": request,
            "title": "Browse Listings",
            "listings": listings,
            "current_user": current_user,
            "filter_material": material or "",
            "filter_location": location or "",
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_listing_form(
    request: Request,
    db: Session = Depends(get_db),
):
    """Show the new listing form with production suggestions."""
    user = require_user(request, db)

    # Fetch user's production capabilities from FIO
    suggestions = []
    if user.fio_api_key:
        client = FIOClient(api_key=user.fio_api_key)
        try:
            buildings = await client.get_user_planet_buildings(user.fio_username)
            recipes = await client.get_building_recipes()
            production_map = build_production_map(buildings, recipes)
            suggestions = sorted(production_map.keys())
        except Exception:
            pass  # Fail silently, user can still add manually
        finally:
            await client.close()

    return templates.TemplateResponse(
        "listings/form.html",
        {
            "request": request,
            "title": "Create Listing",
            "user": user,
            "suggestions": suggestions,
            "listing": None,  # New listing, not editing
        },
    )


@router.post("/new")
async def create_listing(
    request: Request,
    material_ticker: str = Form(...),
    quantity: Optional[int] = Form(None),
    price_type: str = Form(...),
    price_value: Optional[float] = Form(None),
    price_exchange: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    listing_type: str = Form("standing"),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Create a new listing."""
    user = require_user(request, db)

    listing = Listing(
        user_id=user.id,
        material_ticker=material_ticker.upper(),
        quantity=quantity,
        price_type=PriceType(price_type),
        price_value=price_value,
        price_exchange=price_exchange.upper() if price_exchange else None,
        location=location,
        listing_type=ListingType(listing_type),
        notes=notes,
    )
    db.add(listing)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/{listing_id}/edit", response_class=HTMLResponse)
async def edit_listing_form(
    request: Request,
    listing_id: int,
    db: Session = Depends(get_db),
):
    """Show the edit form for a listing."""
    user = require_user(request, db)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your listing")

    return templates.TemplateResponse(
        "listings/form.html",
        {
            "request": request,
            "title": "Edit Listing",
            "user": user,
            "listing": listing,
            "suggestions": [],
        },
    )


@router.post("/{listing_id}/edit")
async def update_listing(
    request: Request,
    listing_id: int,
    material_ticker: str = Form(...),
    quantity: Optional[int] = Form(None),
    price_type: str = Form(...),
    price_value: Optional[float] = Form(None),
    price_exchange: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    listing_type: str = Form("standing"),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Update an existing listing."""
    user = require_user(request, db)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your listing")

    listing.material_ticker = material_ticker.upper()
    listing.quantity = quantity
    listing.price_type = PriceType(price_type)
    listing.price_value = price_value
    listing.price_exchange = price_exchange.upper() if price_exchange else None
    listing.location = location
    listing.listing_type = ListingType(listing_type)
    listing.notes = notes

    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/{listing_id}/delete")
async def delete_listing(
    request: Request,
    listing_id: int,
    db: Session = Depends(get_db),
):
    """Delete a listing."""
    user = require_user(request, db)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your listing")

    db.delete(listing)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)
