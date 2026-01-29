from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..database import get_db
from ..models import User, Listing, Bundle
from ..utils import format_price
from ..services.fio_sync import get_sync_staleness
from ..services.discord_format import render_discord
from ..services.cx_sync import get_cx_prices_bulk, get_sync_age_string as get_cx_sync_age
from ..services.material_sync import get_material_category_map
from ..services.telemetry import increment_stat, Metrics
from ..template_utils import templates, render_template
from .auth import get_current_user

router = APIRouter()


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

    # Get CX prices for calculated price display
    cx_prices = get_cx_prices_bulk(db)
    cx_sync_age = get_cx_sync_age(db)

    # Get material category mapping for colored tickers
    material_categories = get_material_category_map(db)

    return render_template(
        request,
        "profile/public.html",
        {
            "request": request,
            "title": f"{user.fio_username}'s Listings",
            "profile_user": user,
            "listings": listings,
            "bundles": bundles,
            "current_user": current_user,
            "cx_prices": cx_prices,
            "cx_sync_age": cx_sync_age,
            "material_categories": material_categories,
        },
    )


@router.get("/{username}/discord", response_class=PlainTextResponse)
async def discord_copy(
    request: Request,
    username: str,
    db: Session = Depends(get_db),
):
    """Generate Discord-formatted text for copy/paste using user's custom template."""
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

    base_url = str(request.base_url).rstrip("/")

    # Track Discord copy usage
    increment_stat(db, Metrics.DISCORD_COPIES)

    return render_discord(user, listings, base_url)
