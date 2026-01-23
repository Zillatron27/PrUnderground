from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Listing, PriceType
from .auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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

    listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
        .order_by(Listing.updated_at.desc())
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
            "current_user": current_user,
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

    listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id)
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


def format_price(listing: Listing) -> str:
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
