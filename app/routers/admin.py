"""Admin router for statistics dashboard and admin-only features."""

import logging
import os
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import User, Listing, Bundle, UsageStats
from ..admin import is_admin
from ..services.telemetry import get_stats_summary, Metrics
from ..template_utils import templates, render_template
from .auth import get_current_user
from ..scheduler import sync_exchange_prices_job

logger = logging.getLogger(__name__)

router = APIRouter()


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency that requires admin access."""
    user = get_current_user(request, db)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/stats", response_class=HTMLResponse)
async def admin_stats(
    request: Request,
    db: Session = Depends(get_db),
):
    """Admin statistics dashboard."""
    user = require_admin(request, db)

    # Get telemetry summary
    stats = get_stats_summary(db)

    # Get counts from main tables
    total_users = db.query(func.count(User.id)).scalar()
    total_listings = db.query(func.count(Listing.id)).scalar()
    total_bundles = db.query(func.count(Bundle.id)).scalar()

    # Get active users (logged in within last 30 days)
    thirty_days_ago = date.today() - timedelta(days=30)
    # We track active users via the ACTIVE_USERS_DAILY metric
    active_users_month = stats["month"].get(Metrics.ACTIVE_USERS_DAILY, 0)

    # Get recent daily stats for chart data
    today = date.today()
    chart_data = []
    for i in range(30):
        d = today - timedelta(days=29 - i)
        day_stats = db.query(UsageStats).filter(UsageStats.date == d).all()
        day_data = {"date": d.strftime("%Y-%m-%d")}
        for stat in day_stats:
            day_data[stat.metric] = stat.value
        chart_data.append(day_data)

    return render_template(
        request,
        "admin/stats.html",
        {
            "request": request,
            "title": "Admin Stats",
            "current_user": user,
            "stats": stats,
            "total_users": total_users,
            "total_listings": total_listings,
            "total_bundles": total_bundles,
            "active_users_month": active_users_month,
            "chart_data": chart_data,
            "metrics": Metrics,
        },
    )


@router.post("/force-cx-sync", response_class=HTMLResponse)
async def force_cx_sync(
    request: Request,
    db: Session = Depends(get_db),
):
    """Force an immediate CX price sync."""
    user = require_admin(request, db)

    logger.info(f"Admin {user.fio_username} triggered manual CX sync")

    from ..database import SessionLocal
    from ..services.cx_sync import sync_exchange_prices

    sync_db = SessionLocal()
    try:
        inserted, updated = await sync_exchange_prices(sync_db)
        logger.info(f"Manual CX sync complete: {inserted} new, {updated} updated")
        return f'<span class="success-message">CX sync complete: {inserted} inserted, {updated} updated</span>'
    except Exception as e:
        logger.error(f"Manual CX sync failed: {e}")
        return f'<span class="error-message">CX sync failed: {e}</span>'
    finally:
        sync_db.close()


@router.post("/restart", response_class=HTMLResponse)
async def restart_container(
    request: Request,
    db: Session = Depends(get_db),
):
    """Restart the container by exiting cleanly."""
    user = require_admin(request, db)

    logger.info(f"Admin {user.fio_username} triggered container restart")

    # Return response first, then exit
    import asyncio

    async def delayed_exit():
        await asyncio.sleep(0.5)
        logger.info("Exiting process for restart...")
        os._exit(0)

    asyncio.create_task(delayed_exit())

    return '<span class="success-message">Restart initiated. Container will restart shortly...</span>'
