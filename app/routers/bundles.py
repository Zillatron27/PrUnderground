"""Bundles router - CRUD operations for multi-item bundles."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional, List

from ..database import get_db
from ..models import User, Bundle, BundleItem, ListingType
from ..utils import clean_str
from ..audit import log_audit, AuditAction
from ..csrf import verify_csrf
from ..template_utils import templates, render_template
from ..services.planet_sync import get_all_locations_from_db
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

    bundle = Bundle(
        user_id=user.id,
        name=name.strip(),
        description=clean_str(description),
        quantity=quantity,
        price=price,
        currency=currency.upper() if currency else None,
        location=clean_str(location),
        listing_type=ListingType(listing_type),
        expires_at=expires_at_dt,
        notes=clean_str(notes),
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

    # Update bundle fields
    bundle.name = name.strip()
    bundle.description = clean_str(description)
    bundle.quantity = quantity
    bundle.price = price
    bundle.currency = currency.upper() if currency else None
    bundle.location = clean_str(location)
    bundle.listing_type = ListingType(listing_type)
    bundle.expires_at = expires_at_dt
    bundle.notes = clean_str(notes)

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
