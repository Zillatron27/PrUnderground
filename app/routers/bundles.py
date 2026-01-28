"""Bundles router - CRUD operations for multi-item bundles."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional, List

from ..database import get_db
from ..models import User, Bundle, BundleItem, ListingType, BundleStockMode
from ..utils import clean_str
from ..audit import log_audit, AuditAction
from ..csrf import verify_csrf
from ..services.telemetry import increment_stat, Metrics
from ..template_utils import templates, render_template
from ..services.planet_sync import get_all_locations_from_db, get_cx_station_names
from ..fio_client import FIOClient, extract_storage_locations
from ..fio_cache import fio_cache
from ..encryption import decrypt_api_key
from .auth import get_current_user, require_user

router = APIRouter()

# Valid currencies for bundles (no CX-relative pricing)
VALID_CURRENCIES = ["AIC", "CIS", "NCC", "ICA"]


@router.get("/", response_class=HTMLResponse)
async def browse_bundles(
    request: Request,
    location: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Browse all bundles, optionally filtered by location."""
    now = datetime.utcnow()
    query = db.query(Bundle).join(User)

    # Filter out expired bundles
    query = query.filter(
        (Bundle.expires_at.is_(None)) | (Bundle.expires_at > now)
    )

    # Filter by location
    if location:
        query = query.filter(Bundle.location.ilike(f"%{location}%"))

    bundles = query.order_by(Bundle.updated_at.desc()).all()
    current_user = get_current_user(request, db)

    # Get unique locations from active bundles
    location_query = db.query(Bundle).filter(
        (Bundle.expires_at.is_(None)) | (Bundle.expires_at > now)
    )
    all_bundles = location_query.all()
    available_locations = sorted(set(
        b.location for b in all_bundles if b.location
    ))

    return templates.TemplateResponse(
        "bundles/browse.html",
        {
            "request": request,
            "title": "Browse Bundles",
            "bundles": bundles,
            "current_user": current_user,
            "filter_location": location or "",
            "available_locations": available_locations,
        },
    )


@router.get("/{bundle_id}/detail", response_class=HTMLResponse)
async def get_bundle_detail(
    request: Request,
    bundle_id: int,
    db: Session = Depends(get_db),
):
    """HTMX endpoint: Get bundle detail modal content."""
    bundle = db.query(Bundle).filter(Bundle.id == bundle_id).first()

    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    return templates.TemplateResponse(
        "partials/bundle_modal.html",
        {"request": request, "bundle": bundle},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_bundle_form(
    request: Request,
    db: Session = Depends(get_db),
):
    """Show the new bundle form."""
    user = require_user(request, db)

    return render_template(
        request,
        "bundles/form.html",
        {
            "request": request,
            "title": "Create Bundle",
            "user": user,
            "current_user": user,
            "bundle": None,
            "currencies": VALID_CURRENCIES,
            "has_fio_key": bool(user.fio_api_key),
            "stock_modes": BundleStockMode,
        },
    )


@router.get("/api/item-row", response_class=HTMLResponse)
async def get_item_row(
    request: Request,
    index: int = Query(...),
    db: Session = Depends(get_db),
):
    """HTMX endpoint: Get a new item row for dynamic form."""
    require_user(request, db)

    return templates.TemplateResponse(
        "partials/bundle_item_row.html",
        {
            "request": request,
            "index": index,
            "item": None,
        },
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
async def create_bundle(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    quantity: Optional[int] = Form(None),
    price: Optional[float] = Form(None),
    currency: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    listing_type: str = Form("standing"),
    expires_at: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    contact_me: Optional[str] = Form(None),
    stock_mode: str = Form("manual"),
    storage_id: Optional[str] = Form(None),
    storage_name: Optional[str] = Form(None),
    ready_quantity: Optional[int] = Form(None),
    low_stock_threshold: Optional[int] = Form(None),
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Create a new bundle with items."""
    await verify_csrf(request, csrf_token)
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Parse form data for items (item_ticker_0, item_qty_0, etc.)
    form_data = await request.form()
    items = []
    i = 0
    while True:
        ticker_key = f"item_ticker_{i}"
        qty_key = f"item_qty_{i}"
        if ticker_key not in form_data:
            break
        ticker = form_data.get(ticker_key, "").strip().upper()
        qty_str = form_data.get(qty_key, "")
        if ticker:
            try:
                qty = int(qty_str) if qty_str else 1
            except ValueError:
                qty = 1
            items.append({"ticker": ticker, "quantity": qty})
        i += 1

    if not items:
        raise HTTPException(status_code=400, detail="Bundle must have at least one item")

    # Handle "contact me" pricing
    if contact_me:
        price = None
        currency = None

    # Parse expiry date
    expires_at_dt = None
    if expires_at and listing_type == "special":
        try:
            expires_at_dt = datetime.strptime(expires_at, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # Parse stock mode
    try:
        bundle_stock_mode = BundleStockMode(stock_mode)
    except ValueError:
        bundle_stock_mode = BundleStockMode.MANUAL

    # Set fields based on stock mode
    bundle_quantity = None
    bundle_storage_id = None
    bundle_storage_name = None
    bundle_ready_quantity = None

    if bundle_stock_mode == BundleStockMode.MANUAL:
        bundle_quantity = quantity
    elif bundle_stock_mode == BundleStockMode.FIO_SYNC:
        bundle_storage_id = clean_str(storage_id)
        bundle_storage_name = clean_str(storage_name)
    elif bundle_stock_mode == BundleStockMode.MADE_TO_ORDER:
        bundle_ready_quantity = ready_quantity

    bundle = Bundle(
        user_id=user.id,
        name=name.strip(),
        description=clean_str(description),
        quantity=bundle_quantity,
        price=price,
        currency=currency.upper() if currency else None,
        location=clean_str(location),
        listing_type=ListingType(listing_type),
        expires_at=expires_at_dt,
        notes=clean_str(notes),
        stock_mode=bundle_stock_mode,
        storage_id=bundle_storage_id,
        storage_name=bundle_storage_name,
        ready_quantity=bundle_ready_quantity,
        low_stock_threshold=low_stock_threshold,
    )
    db.add(bundle)
    db.flush()  # Get the bundle ID before adding items

    for item in items:
        bundle_item = BundleItem(
            bundle_id=bundle.id,
            material_ticker=item["ticker"],
            quantity=item["quantity"],
        )
        db.add(bundle_item)

    db.commit()
    db.refresh(bundle)

    log_audit(
        db,
        AuditAction.BUNDLE_CREATED,
        user_id=user.id,
        entity_type="bundle",
        entity_id=bundle.id,
        details={"name": bundle.name, "item_count": len(items)},
    )
    increment_stat(db, Metrics.BUNDLES_CREATED)

    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/{bundle_id}/edit", response_class=HTMLResponse)
async def edit_bundle_form(
    request: Request,
    bundle_id: int,
    db: Session = Depends(get_db),
):
    """Show the edit form for a bundle."""
    user = require_user(request, db)
    bundle = db.query(Bundle).filter(Bundle.id == bundle_id).first()

    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your bundle")

    return render_template(
        request,
        "bundles/form.html",
        {
            "request": request,
            "title": "Edit Bundle",
            "user": user,
            "current_user": user,
            "bundle": bundle,
            "currencies": VALID_CURRENCIES,
            "has_fio_key": bool(user.fio_api_key),
            "stock_modes": BundleStockMode,
        },
    )


@router.post("/{bundle_id}/edit")
async def update_bundle(
    request: Request,
    bundle_id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    quantity: Optional[int] = Form(None),
    price: Optional[float] = Form(None),
    currency: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    listing_type: str = Form("standing"),
    expires_at: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    contact_me: Optional[str] = Form(None),
    stock_mode: str = Form("manual"),
    storage_id: Optional[str] = Form(None),
    storage_name: Optional[str] = Form(None),
    ready_quantity: Optional[int] = Form(None),
    low_stock_threshold: Optional[int] = Form(None),
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Update an existing bundle."""
    await verify_csrf(request, csrf_token)
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    bundle = db.query(Bundle).filter(Bundle.id == bundle_id).first()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your bundle")

    # Parse form data for items
    form_data = await request.form()
    items = []
    i = 0
    while True:
        ticker_key = f"item_ticker_{i}"
        qty_key = f"item_qty_{i}"
        if ticker_key not in form_data:
            break
        ticker = form_data.get(ticker_key, "").strip().upper()
        qty_str = form_data.get(qty_key, "")
        if ticker:
            try:
                qty = int(qty_str) if qty_str else 1
            except ValueError:
                qty = 1
            items.append({"ticker": ticker, "quantity": qty})
        i += 1

    if not items:
        raise HTTPException(status_code=400, detail="Bundle must have at least one item")

    # Handle "contact me" pricing
    if contact_me:
        price = None
        currency = None

    # Parse expiry date
    expires_at_dt = None
    if expires_at and listing_type == "special":
        try:
            expires_at_dt = datetime.strptime(expires_at, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # Parse stock mode
    try:
        bundle_stock_mode = BundleStockMode(stock_mode)
    except ValueError:
        bundle_stock_mode = BundleStockMode.MANUAL

    # Set fields based on stock mode
    bundle_quantity = None
    bundle_storage_id = None
    bundle_storage_name = None
    bundle_ready_quantity = None
    bundle_available_quantity = None

    if bundle_stock_mode == BundleStockMode.MANUAL:
        bundle_quantity = quantity
    elif bundle_stock_mode == BundleStockMode.FIO_SYNC:
        bundle_storage_id = clean_str(storage_id)
        bundle_storage_name = clean_str(storage_name)
        # Keep existing available_quantity if same storage, otherwise reset
        if bundle.storage_id == bundle_storage_id:
            bundle_available_quantity = bundle.available_quantity
    elif bundle_stock_mode == BundleStockMode.MADE_TO_ORDER:
        bundle_ready_quantity = ready_quantity

    # Update bundle fields
    bundle.name = name.strip()
    bundle.description = clean_str(description)
    bundle.quantity = bundle_quantity
    bundle.price = price
    bundle.currency = currency.upper() if currency else None
    bundle.location = clean_str(location)
    bundle.listing_type = ListingType(listing_type)
    bundle.expires_at = expires_at_dt
    bundle.notes = clean_str(notes)
    bundle.stock_mode = bundle_stock_mode
    bundle.storage_id = bundle_storage_id
    bundle.storage_name = bundle_storage_name
    bundle.ready_quantity = bundle_ready_quantity
    bundle.available_quantity = bundle_available_quantity
    bundle.low_stock_threshold = low_stock_threshold

    # Replace all items (delete old, add new)
    for old_item in bundle.items:
        db.delete(old_item)

    for item in items:
        bundle_item = BundleItem(
            bundle_id=bundle.id,
            material_ticker=item["ticker"],
            quantity=item["quantity"],
        )
        db.add(bundle_item)

    db.commit()

    log_audit(
        db,
        AuditAction.BUNDLE_UPDATED,
        user_id=user.id,
        entity_type="bundle",
        entity_id=bundle.id,
        details={"name": bundle.name, "item_count": len(items)},
    )

    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/api/inventory-preview", response_class=HTMLResponse)
async def get_inventory_preview(
    request: Request,
    storage_id: str = Query(...),
    items: str = Query(...),
    db: Session = Depends(get_db),
):
    """HTMX endpoint: Get inventory preview for bundle items."""
    import json

    user = require_user(request, db)

    # Parse items JSON
    try:
        item_list = json.loads(items)
    except json.JSONDecodeError:
        return HTMLResponse("<p class='help-text error-text'>Invalid items format</p>")

    if not item_list:
        return HTMLResponse("")

    # Get inventory from FIO cache (or fetch if needed)
    inventory = {}
    if user.fio_api_key:
        # Check cached storage data first
        cached_storage = fio_cache.get_storage(user.fio_username)
        if cached_storage is not None:
            # Find the specific storage and extract inventory
            for storage in cached_storage:
                sid = storage.get("AddressableId") or storage.get("StoreId")
                if sid == storage_id:
                    for inv_item in storage.get("StorageItems", []):
                        ticker = inv_item.get("MaterialTicker", "")
                        qty = inv_item.get("MaterialAmount", 0)
                        if ticker:
                            inventory[ticker] = qty
                    break
        else:
            # Try to fetch from FIO
            try:
                decrypted_key = decrypt_api_key(user.fio_api_key)
                client = FIOClient(api_key=decrypted_key)
                raw_storages = await client.get_user_storage(user.fio_username)
                await client.close()

                # Cache the storage data
                fio_cache.set_storage(user.fio_username, raw_storages)

                # Find the specific storage and extract inventory
                for storage in raw_storages:
                    sid = storage.get("AddressableId") or storage.get("StoreId")
                    if sid == storage_id:
                        for inv_item in storage.get("StorageItems", []):
                            ticker = inv_item.get("MaterialTicker", "")
                            qty = inv_item.get("MaterialAmount", 0)
                            if ticker:
                                inventory[ticker] = qty
                        break
            except Exception:
                pass

    # Calculate availability for each item
    preview_data = []
    min_can_make = None

    for item in item_list:
        ticker = item.get("ticker", "").upper()
        required = item.get("qty", 1)
        in_stock = inventory.get(ticker, 0)
        can_make = in_stock // required if required > 0 else 0

        preview_data.append({
            "ticker": ticker,
            "required": required,
            "in_stock": in_stock,
            "can_make": can_make,
        })

        if min_can_make is None or can_make < min_can_make:
            min_can_make = can_make

    # Mark limiting items (only meaningful with multiple items)
    for item in preview_data:
        item["is_limiting"] = len(preview_data) > 1 and item["can_make"] == min_can_make

    return templates.TemplateResponse(
        "partials/bundle_inventory_preview.html",
        {
            "request": request,
            "items": preview_data,
            "can_make": min_can_make or 0,
        },
    )


@router.post("/{bundle_id}/delete")
async def delete_bundle(
    request: Request,
    bundle_id: int,
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Delete a bundle."""
    await verify_csrf(request, csrf_token)
    user = require_user(request, db)
    bundle = db.query(Bundle).filter(Bundle.id == bundle_id).first()

    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your bundle")

    # Capture details before deletion
    bundle_name = bundle.name
    deleted_id = bundle.id

    db.delete(bundle)  # Cascade deletes bundle items
    db.commit()

    log_audit(
        db,
        AuditAction.BUNDLE_DELETED,
        user_id=user.id,
        entity_type="bundle",
        entity_id=deleted_id,
        details={"name": bundle_name},
    )

    return RedirectResponse(url="/dashboard", status_code=303)
