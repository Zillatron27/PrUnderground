from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..database import get_db
from ..models import User, Listing, Bundle
from ..utils import format_price, get_stock_status
from ..services.fio_sync import get_sync_staleness
from .auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["format_price"] = format_price
templates.env.globals["get_stock_status"] = get_stock_status
templates.env.globals["get_sync_staleness"] = get_sync_staleness


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
    bundles = (
        db.query(Bundle)
        .filter(Bundle.user_id == user.id)
        .filter(or_(Bundle.expires_at.is_(None), Bundle.expires_at > now))
        .order_by(Bundle.updated_at.desc())
        .all()
    )
    current_user = get_current_user(request, db)

    return templates.TemplateResponse(
        "profile/public.html",
        {
            "request": request,
            "title": f"{user.fio_username}'s Listings",
            "profile_user": user,
            "listings": listings,
            "bundles": bundles,
            "current_user": current_user,
            "format_price": format_price,
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

    # Group listings by location
    by_location = {}
    for listing in listings:
        loc = listing.storage_name or listing.location or "Unknown"
        if loc not in by_location:
            by_location[loc] = []
        by_location[loc].append(listing)

    # Build Discord message
    date_str = datetime.utcnow().strftime("%d %b %Y")
    lines = [
        f"🚀 **[{user.company_code or '???'}] {user.fio_username}** - Updated {date_str}",
    ]

    for location, loc_listings in by_location.items():
        lines.append("")
        lines.append(f"**{location}:**")
        for listing in sorted(loc_listings, key=lambda l: l.material_ticker):
            price_str = format_price(listing)
            qty = listing.available_quantity if listing.available_quantity is not None else listing.quantity
            qty_str = f" × {qty:,}" if qty else ""
            lines.append(f"• {listing.material_ticker}{qty_str} @ {price_str}")

    # Add link to full listings
    base_url = str(request.base_url).rstrip("/")
    lines.append("")
    lines.append(f"📋 Full listings: {base_url}/u/{username}")

    return "\n".join(lines)
