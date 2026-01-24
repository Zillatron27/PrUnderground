from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..database import get_db
from ..models import User, Listing, PriceType
from ..utils import format_price
from .auth import get_current_user
from ..fio_cache import fio_cache
from ..fio_client import FIOClient, extract_storage_locations

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["format_price"] = format_price


async def get_stock_status_for_listings(user: User, listings: list) -> dict:
    """
    Fetch FIO inventory and compute stock status for each listing.
    Returns dict mapping listing.id to status: 'ok', 'low', or 'out'.
    """
    stock_status = {}

    if not user.fio_api_key:
        return stock_status

    # Try cache first
    storage_locations = fio_cache.get_storage_locations(user.fio_username)

    if storage_locations is None:
        # Fetch from FIO
        client = FIOClient(api_key=user.fio_api_key)
        try:
            raw_storages = await client.get_user_storage(user.fio_username)
            sites = await client.get_user_sites(user.fio_username)
            warehouses = await client.get_user_warehouses(user.fio_username)
            storage_locations = extract_storage_locations(raw_storages, sites, warehouses)
            # Cache it
            fio_cache.set_storage(user.fio_username, raw_storages)
            fio_cache.set_sites(user.fio_username, sites)
            fio_cache.set_warehouses(user.fio_username, warehouses)
            fio_cache.set_storage_locations(user.fio_username, storage_locations)
        except Exception:
            return stock_status
        finally:
            await client.close()

    # Build inventory map
    storage_inventory = {}
    for storage in storage_locations:
        storage_inventory[storage["addressable_id"]] = storage["items"]

    # Compute status for each listing
    for listing in listings:
        if listing.storage_id and listing.storage_id in storage_inventory:
            items = storage_inventory[listing.storage_id]
            actual = items.get(listing.material_ticker, 0)
            reserve = listing.reserve_quantity or 0
            available = max(0, actual - reserve)

            if available == 0:
                stock_status[listing.id] = "out"
            elif available <= 10:
                stock_status[listing.id] = "low"
            else:
                stock_status[listing.id] = "ok"

    return stock_status


@router.get("/{username}", response_class=HTMLResponse)
async def public_profile(
    request: Request,
    username: str,
    db: Session = Depends(get_db),
):
    """Public profile page showing a user's listings."""
    user = db.query(User).filter(User.fio_username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
        .filter(or_(Listing.expires_at.is_(None), Listing.expires_at > now))
        .order_by(Listing.updated_at.desc())
        .all()
    )
    current_user = get_current_user(request, db)

    # Fetch live stock status from FIO
    stock_status = await get_stock_status_for_listings(user, listings)

    return templates.TemplateResponse(
        "profile/public.html",
        {
            "request": request,
            "title": f"{user.fio_username}'s Listings",
            "profile_user": user,
            "listings": listings,
            "current_user": current_user,
            "format_price": format_price,
            "stock_status": stock_status,
        },
    )


@router.get("/{username}/discord", response_class=PlainTextResponse)
async def discord_copy(
    request: Request,
    username: str,
    db: Session = Depends(get_db),
):
    """Generate Discord-formatted text for copy/paste."""
    user = db.query(User).filter(User.fio_username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
        .filter(or_(Listing.expires_at.is_(None), Listing.expires_at > now))
        .order_by(Listing.material_ticker)
        .all()
    )

    if not listings:
        return f"**[{user.company_code or '???'}] {user.fio_username}** has no active listings."

    # Build Discord message
    date_str = datetime.utcnow().strftime("%d %b %Y")
    lines = [
        f"🚀 **[{user.company_code or '???'}] {user.fio_username}** - Updated {date_str}",
        "",
        "**Selling:**",
    ]

    for listing in listings:
        price_str = format_price(listing)
        location_str = f" ({listing.location})" if listing.location else ""
        qty_str = f" × {listing.quantity:,}" if listing.quantity else ""
        lines.append(f"• {listing.material_ticker}{qty_str} @ {price_str}{location_str}")

    # Add link to full listings
    base_url = str(request.base_url).rstrip("/")
    lines.append("")
    lines.append(f"📋 Full listings: {base_url}/u/{username}")

    return "\n".join(lines)
