from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import User, Listing, PriceType, ListingType
from ..fio_client import FIOClient, extract_active_production, extract_storage_locations
from ..fio_cache import fio_cache
from ..services.material_sync import get_all_materials_from_db, get_material_categories, get_material_category_map
from ..services.planet_sync import get_all_locations_from_db, get_cx_station_names
from ..utils import format_price, clean_str
from ..services.fio_sync import get_sync_staleness
from ..services.cx_sync import get_cx_prices_bulk, get_sync_age_string as get_cx_sync_age
from ..audit import log_audit, AuditAction
from ..csrf import verify_csrf
from ..services.telemetry import increment_stat, Metrics
from ..template_utils import templates, render_template
from ..encryption import decrypt_api_key
from .auth import get_current_user, require_user

router = APIRouter()


# Valid sortable columns and their SQLAlchemy column references
SORTABLE_COLUMNS = {
    "material": Listing.material_ticker,
    "quantity": Listing.available_quantity,
    "price": Listing.price_value,
    "location": Listing.storage_name,
    "updated": Listing.updated_at,
}


def parse_sort_param(sort_param: Optional[str]) -> list[tuple[str, str]]:
    """Parse sort parameter like 'material:asc,location:desc' into list of tuples."""
    if not sort_param:
        return [("updated", "desc")]

    result = []
    for part in sort_param.split(","):
        part = part.strip()
        if ":" in part:
            col, direction = part.split(":", 1)
            col = col.strip().lower()
            direction = direction.strip().lower()
            if col in SORTABLE_COLUMNS and direction in ("asc", "desc"):
                result.append((col, direction))
        else:
            col = part.strip().lower()
            if col in SORTABLE_COLUMNS:
                result.append((col, "asc"))

    return result if result else [("updated", "desc")]


@router.get("/", response_class=HTMLResponse)
async def browse_listings(
    request: Request,
    material: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
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

    # Parse and apply multi-column sorting
    sort_spec = parse_sort_param(sort)
    for col_name, direction in sort_spec:
        column = SORTABLE_COLUMNS[col_name]
        if col_name == "price":
            # Special handling: contact_me (NULL price_value) sorts last
            from sqlalchemy import case
            # For ascending: NULLs last (high value), for descending: NULLs last (low value)
            if direction == "asc":
                query = query.order_by(
                    case((Listing.price_type == PriceType.CONTACT_ME, 1), else_=0),
                    column.asc()
                )
            else:
                query = query.order_by(
                    case((Listing.price_type == PriceType.CONTACT_ME, 1), else_=0),
                    column.desc()
                )
        else:
            if direction == "asc":
                query = query.order_by(column.asc())
            else:
                query = query.order_by(column.desc())

    listings = query.all()
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

    # Get CX prices for calculated price display
    cx_prices = get_cx_prices_bulk(db)
    cx_sync_age = get_cx_sync_age(db)

    # Get material category mapping for colored tickers
    material_categories = get_material_category_map(db)

    # Track page view
    increment_stat(db, Metrics.LISTINGS_VIEWED)

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
            "sort_spec": sort_spec,
            "sort_param": sort or "",
            "cx_prices": cx_prices,
            "cx_sync_age": cx_sync_age,
            "material_categories": material_categories,
        },
    )


@router.get("/api/materials", response_class=HTMLResponse)
async def get_materials_datalist(
    request: Request,
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """HTMX endpoint: Get all materials for datalist from database."""
    all_materials = get_all_materials_from_db(db, category=category)

    return templates.TemplateResponse(
        "partials/materials_datalist.html",
        {"request": request, "all_materials": all_materials},
    )


@router.get("/api/locations", response_class=HTMLResponse)
async def get_locations_datalist(
    request: Request,
    db: Session = Depends(get_db),
):
    """HTMX endpoint: Get all locations for datalist from database."""
    locations = get_all_locations_from_db(db)

    return templates.TemplateResponse(
        "partials/locations_datalist.html",
        {"request": request, "locations": locations},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_listing_form(
    request: Request,
    db: Session = Depends(get_db),
):
    """Show the new listing form. FIO data loaded via HTMX."""
    user = require_user(request, db)

    return render_template(
        request,
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
            # Fetch from FIO (decrypt API key first)
            try:
                decrypted_key = decrypt_api_key(user.fio_api_key)
                client = FIOClient(api_key=decrypted_key)
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
            # Fetch from FIO (decrypt API key first)
            try:
                decrypted_key = decrypt_api_key(user.fio_api_key)
                client = FIOClient(api_key=decrypted_key)
                raw_storages = await client.get_user_storage(user.fio_username)
                sites = await client.get_user_sites(user.fio_username)
                warehouses = await client.get_user_warehouses(user.fio_username)
                cx_names = get_cx_station_names(db)
                all_storages = extract_storage_locations(
                    raw_storages, sites, warehouses, cx_names
                )
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
    cx_offset_type: Optional[str] = Form("percent"),
    location: Optional[str] = Form(None),
    listing_type: str = Form("standing"),
    notes: Optional[str] = Form(None),
    storage_id: Optional[str] = Form(None),
    storage_name: Optional[str] = Form(None),
    reserve_quantity: Optional[int] = Form(None),
    low_stock_threshold: Optional[int] = Form(10),
    expires_at: Optional[str] = Form(None),
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Create a new listing."""
    await verify_csrf(request, csrf_token)
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

    listing = Listing(
        user_id=user.id,
        material_ticker=material_ticker.upper(),
        quantity=quantity,
        price_type=PriceType(price_type),
        price_value=price_value,
        price_exchange=price_exchange.upper() if price_exchange else None,
        price_cx_is_absolute=(cx_offset_type == "absolute"),
        location=clean_str(location),
        listing_type=ListingType(listing_type),
        notes=clean_str(notes),
        storage_id=clean_str(storage_id),
        storage_name=clean_str(storage_name),
        reserve_quantity=reserve_quantity if reserve_quantity else 0,
        low_stock_threshold=low_stock_threshold if low_stock_threshold is not None else 10,
        expires_at=expires_at_dt,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    log_audit(
        db,
        AuditAction.LISTING_CREATED,
        user_id=user.id,
        entity_type="listing",
        entity_id=listing.id,
        details={"material": material_ticker.upper()},
    )
    increment_stat(db, Metrics.LISTINGS_CREATED)

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

    return render_template(
        request,
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
    cx_offset_type: Optional[str] = Form("percent"),
    location: Optional[str] = Form(None),
    listing_type: str = Form("standing"),
    notes: Optional[str] = Form(None),
    storage_id: Optional[str] = Form(None),
    storage_name: Optional[str] = Form(None),
    reserve_quantity: Optional[int] = Form(None),
    low_stock_threshold: Optional[int] = Form(10),
    expires_at: Optional[str] = Form(None),
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Update an existing listing."""
    await verify_csrf(request, csrf_token)
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

    listing.material_ticker = material_ticker.upper()
    listing.quantity = quantity
    listing.price_type = PriceType(price_type)
    listing.price_value = price_value
    listing.price_exchange = price_exchange.upper() if price_exchange else None
    listing.price_cx_is_absolute = (cx_offset_type == "absolute")
    listing.location = clean_str(location)
    listing.listing_type = ListingType(listing_type)
    listing.notes = clean_str(notes)
    listing.storage_id = clean_str(storage_id)
    listing.storage_name = clean_str(storage_name)
    listing.reserve_quantity = reserve_quantity if reserve_quantity else 0
    listing.low_stock_threshold = low_stock_threshold if low_stock_threshold is not None else 10
    listing.expires_at = expires_at_dt

    db.commit()

    log_audit(
        db,
        AuditAction.LISTING_UPDATED,
        user_id=user.id,
        entity_type="listing",
        entity_id=listing.id,
        details={"material": material_ticker.upper()},
    )

    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/{listing_id}/delete")
async def delete_listing(
    request: Request,
    listing_id: int,
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Delete a listing."""
    await verify_csrf(request, csrf_token)
    user = require_user(request, db)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your listing")

    # Capture details before deletion
    material = listing.material_ticker
    deleted_id = listing.id

    db.delete(listing)
    db.commit()

    log_audit(
        db,
        AuditAction.LISTING_DELETED,
        user_id=user.id,
        entity_type="listing",
        entity_id=deleted_id,
        details={"material": material},
    )

    return RedirectResponse(url="/dashboard", status_code=303)
