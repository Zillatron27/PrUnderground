from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import User, Listing, PriceType, ListingType
from ..schemas import ListingCreate, ListingUpdate
from ..fio_client import FIOClient, extract_active_production, extract_storage_locations
from ..fio_cache import fio_cache
from ..utils import format_price
from .auth import get_current_user, require_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["format_price"] = format_price


@router.get("/", response_class=HTMLResponse)
async def browse_listings(
    request: Request,
    material: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Browse all listings, optionally filtered. Materials datalist loaded via HTMX."""
    now = datetime.utcnow()
    query = db.query(Listing).join(User)

    # Filter out expired listings
    query = query.filter(
        (Listing.expires_at.is_(None)) | (Listing.expires_at > now)
    )

    # Filter by materials (comma-separated)
    material_list = []
    if material:
        # Parse comma-separated materials, strip whitespace, uppercase
        material_list = [m.strip().upper() for m in material.split(",") if m.strip()]
        if material_list:
            query = query.filter(Listing.material_ticker.in_(material_list))

    # Filter by location (matches storage_name OR location)
    if location:
        query = query.filter(
            (Listing.storage_name.ilike(f"%{location}%")) |
            (Listing.location.ilike(f"%{location}%"))
        )

    listings = query.order_by(Listing.updated_at.desc()).all()
    current_user = get_current_user(request, db)

    # Get unique locations from active listings (from DB, no FIO call)
    location_query = db.query(Listing).filter(
        (Listing.expires_at.is_(None)) | (Listing.expires_at > now)
    )
    all_listings = location_query.all()
    available_locations = sorted(set(
        l.storage_name or l.location
        for l in all_listings
        if l.storage_name or l.location
    ))

    return templates.TemplateResponse(
        "listings/browse.html",
        {
            "request": request,
            "title": "Browse Listings",
            "listings": listings,
            "current_user": current_user,
            "filter_material": material or "",
            "filter_location": location or "",
            "available_locations": available_locations,
        },
    )


@router.get("/api/materials", response_class=HTMLResponse)
async def get_materials_datalist(request: Request):
    """HTMX endpoint: Get all materials for datalist (cached)."""
    import re

    def format_name(name: str) -> str:
        spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        return spaced.title()

    # Check cache first
    all_materials = fio_cache.get_all_materials()

    if all_materials is None:
        # Fetch from FIO
        try:
            client = FIOClient()
            raw_materials = await client.get_all_materials()
            all_materials = sorted(
                [{"ticker": m["Ticker"], "name": format_name(m["Name"])} for m in raw_materials],
                key=lambda x: x["ticker"]
            )
            fio_cache.set_all_materials(all_materials)
            await client.close()
        except Exception:
            all_materials = []

    return templates.TemplateResponse(
        "partials/materials_datalist.html",
        {"request": request, "all_materials": all_materials},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_listing_form(
    request: Request,
    db: Session = Depends(get_db),
):
    """Show the new listing form. FIO data loaded via HTMX."""
    user = require_user(request, db)

    return templates.TemplateResponse(
        "listings/form.html",
        {
            "request": request,
            "title": "Create Listing",
            "user": user,
            "current_user": user,
            "listing": None,  # New listing, not editing
        },
    )


@router.get("/api/suggestions", response_class=HTMLResponse)
async def get_suggestions_datalist(request: Request, db: Session = Depends(get_db)):
    """HTMX endpoint: Get production suggestions for material picker (cached)."""
    user = require_user(request, db)

    suggestions = []
    if user.fio_api_key:
        # Check cache first
        cached = fio_cache.get_suggestions(user.fio_username)
        if cached is not None:
            suggestions = cached
        else:
            # Fetch from FIO
            try:
                client = FIOClient(api_key=user.fio_api_key)
                production_lines = await client.get_user_production(user.fio_username)
                suggestions = sorted(extract_active_production(production_lines))
                fio_cache.set_suggestions(user.fio_username, suggestions)
                await client.close()
            except Exception:
                pass

    return templates.TemplateResponse(
        "partials/suggestions_datalist.html",
        {"request": request, "suggestions": suggestions},
    )


@router.get("/api/storages", response_class=HTMLResponse)
async def get_storages_select(
    request: Request,
    db: Session = Depends(get_db),
    selected: Optional[str] = Query(None),
):
    """HTMX endpoint: Get storage locations for dropdown (cached)."""
    user = require_user(request, db)

    storages = []
    if user.fio_api_key:
        # Check cache first
        cached = fio_cache.get_storage_locations(user.fio_username)
        if cached is not None:
            storages = [s for s in cached if s["type"] in ("WAREHOUSE_STORE", "STORE")]
        else:
            # Fetch from FIO
            try:
                client = FIOClient(api_key=user.fio_api_key)
                raw_storages = await client.get_user_storage(user.fio_username)
                sites = await client.get_user_sites(user.fio_username)
                warehouses = await client.get_user_warehouses(user.fio_username)
                all_storages = extract_storage_locations(raw_storages, sites, warehouses)
                fio_cache.set_storage_locations(user.fio_username, all_storages)
                storages = [s for s in all_storages if s["type"] in ("WAREHOUSE_STORE", "STORE")]
                await client.close()
            except Exception:
                pass

    return templates.TemplateResponse(
        "partials/storages_select.html",
        {"request": request, "storages": storages, "selected": selected},
    )


@router.post("/new")
async def create_listing(
    request: Request,
    material_ticker: str = Form(...),
    quantity: Optional[int] = Form(None),
    price_type: str = Form(...),
    price_value_absolute: Optional[float] = Form(None),
    price_value_cx: Optional[float] = Form(None),
    price_exchange: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    listing_type: str = Form("standing"),
    notes: Optional[str] = Form(None),
    storage_id: Optional[str] = Form(None),
    storage_name: Optional[str] = Form(None),
    reserve_quantity: Optional[int] = Form(None),
    expires_at: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Create a new listing."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Select the right price value based on price type
    if price_type == "absolute":
        price_value = price_value_absolute
    elif price_type == "cx_relative":
        price_value = price_value_cx
    else:
        price_value = None

    # Parse expiry date (set to end of day)
    expires_at_dt = None
    if expires_at and listing_type == "special":
        try:
            expires_at_dt = datetime.strptime(expires_at, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # Sanitize optional string fields (empty strings and "None" become None)
    def clean_str(val: Optional[str]) -> Optional[str]:
        if not val or val.strip() == "" or val.strip().lower() == "none":
            return None
        return val.strip()

    listing = Listing(
        user_id=user.id,
        material_ticker=material_ticker.upper(),
        quantity=quantity,
        price_type=PriceType(price_type),
        price_value=price_value,
        price_exchange=price_exchange.upper() if price_exchange else None,
        location=clean_str(location),
        listing_type=ListingType(listing_type),
        notes=clean_str(notes),
        storage_id=clean_str(storage_id),
        storage_name=clean_str(storage_name),
        reserve_quantity=reserve_quantity if reserve_quantity else 0,
        expires_at=expires_at_dt,
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
    """Show the edit form for a listing. FIO data loaded via HTMX."""
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
            "current_user": user,
            "listing": listing,
        },
    )


@router.post("/{listing_id}/edit")
async def update_listing(
    request: Request,
    listing_id: int,
    material_ticker: str = Form(...),
    quantity: Optional[int] = Form(None),
    price_type: str = Form(...),
    price_value_absolute: Optional[float] = Form(None),
    price_value_cx: Optional[float] = Form(None),
    price_exchange: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    listing_type: str = Form("standing"),
    notes: Optional[str] = Form(None),
    storage_id: Optional[str] = Form(None),
    storage_name: Optional[str] = Form(None),
    reserve_quantity: Optional[int] = Form(None),
    expires_at: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Update an existing listing."""
    # Select the right price value based on price type
    if price_type == "absolute":
        price_value = price_value_absolute
    elif price_type == "cx_relative":
        price_value = price_value_cx
    else:
        price_value = None

    # Parse expiry date (set to end of day)
    expires_at_dt = None
    if expires_at and listing_type == "special":
        try:
            expires_at_dt = datetime.strptime(expires_at, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your listing")

    # Sanitize optional string fields (empty strings and "None" become None)
    def clean_str(val: Optional[str]) -> Optional[str]:
        if not val or val.strip() == "" or val.strip().lower() == "none":
            return None
        return val.strip()

    listing.material_ticker = material_ticker.upper()
    listing.quantity = quantity
    listing.price_type = PriceType(price_type)
    listing.price_value = price_value
    listing.price_exchange = price_exchange.upper() if price_exchange else None
    listing.location = clean_str(location)
    listing.listing_type = ListingType(listing_type)
    listing.notes = clean_str(notes)
    listing.storage_id = clean_str(storage_id)
    listing.storage_name = clean_str(storage_name)
    listing.reserve_quantity = reserve_quantity if reserve_quantity else 0
    listing.expires_at = expires_at_dt

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
