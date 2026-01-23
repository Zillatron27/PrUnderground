from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import User, Listing, PriceType, ListingType
from ..schemas import ListingCreate, ListingUpdate
from ..fio_client import FIOClient, extract_active_production, extract_storage_locations
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

    # Fetch what user is actually producing from FIO
    suggestions = []
    storages = []
    if user.fio_api_key:
        client = FIOClient(api_key=user.fio_api_key)
        try:
            production_lines = await client.get_user_production(user.fio_username)
            active_materials = extract_active_production(production_lines)
            suggestions = sorted(active_materials)

            # Fetch storage locations
            raw_storages = await client.get_user_storage(user.fio_username)
            sites = await client.get_user_sites(user.fio_username)
            warehouses = await client.get_user_warehouses(user.fio_username)
            storages = extract_storage_locations(raw_storages, sites, warehouses)
            # Filter to only WAREHOUSE_STORE and STORE types (skip fuel/ship stores)
            storages = [s for s in storages if s["type"] in ("WAREHOUSE_STORE", "STORE")]
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
            "storages": storages,
            "listing": None,  # New listing, not editing
        },
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
        storage_id=storage_id if storage_id else None,
        storage_name=storage_name if storage_name else None,
        reserve_quantity=reserve_quantity if reserve_quantity else 0,
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

    # Fetch storage locations for the dropdown
    storages = []
    if user.fio_api_key:
        client = FIOClient(api_key=user.fio_api_key)
        try:
            raw_storages = await client.get_user_storage(user.fio_username)
            sites = await client.get_user_sites(user.fio_username)
            warehouses = await client.get_user_warehouses(user.fio_username)
            storages = extract_storage_locations(raw_storages, sites, warehouses)
            storages = [s for s in storages if s["type"] in ("WAREHOUSE_STORE", "STORE")]
        except Exception:
            pass
        finally:
            await client.close()

    return templates.TemplateResponse(
        "listings/form.html",
        {
            "request": request,
            "title": "Edit Listing",
            "user": user,
            "listing": listing,
            "suggestions": [],
            "storages": storages,
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

    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
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
    listing.storage_id = storage_id if storage_id else None
    listing.storage_name = storage_name if storage_name else None
    listing.reserve_quantity = reserve_quantity if reserve_quantity else 0

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
