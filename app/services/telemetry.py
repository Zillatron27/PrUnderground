"""Usage telemetry service for anonymous metrics tracking."""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import UsageStats

logger = logging.getLogger(__name__)


def increment_stat(db: Session, metric: str, amount: int = 1) -> None:
    """
    Increment a daily counter for the given metric.

    This is an upsert operation - creates the row if it doesn't exist,
    otherwise increments the value.

    Args:
        db: Database session
        metric: The metric name (e.g., "listings_created", "discord_copies")
        amount: Amount to increment by (default 1)
    """
    today = date.today()

    try:
        # Try to find existing record
        stat = db.query(UsageStats).filter(
            UsageStats.date == today,
            UsageStats.metric == metric
        ).first()

        if stat:
            stat.value += amount
        else:
            stat = UsageStats(
                date=today,
                metric=metric,
                value=amount
            )
            db.add(stat)

        db.commit()
    except Exception as e:
        logger.error(f"Failed to increment stat {metric}: {e}")
        db.rollback()


def get_stats_for_period(
    db: Session,
    start_date: date,
    end_date: date,
    metrics: Optional[list[str]] = None
) -> dict[str, dict[date, int]]:
    """
    Get stats for a date range, grouped by metric.

    Args:
        db: Database session
        start_date: Start of period (inclusive)
        end_date: End of period (inclusive)
        metrics: Optional list of metric names to filter

    Returns:
        Dict mapping metric -> (date -> value)
    """
    query = db.query(UsageStats).filter(
        UsageStats.date >= start_date,
        UsageStats.date <= end_date
    )

    if metrics:
        query = query.filter(UsageStats.metric.in_(metrics))

    stats = query.all()

    result: dict[str, dict[date, int]] = {}
    for stat in stats:
        if stat.metric not in result:
            result[stat.metric] = {}
        result[stat.metric][stat.date] = stat.value

    return result


def get_total_for_period(
    db: Session,
    metric: str,
    start_date: date,
    end_date: date
) -> int:
    """
    Get the sum of a metric over a date range.

    Args:
        db: Database session
        metric: The metric name
        start_date: Start of period (inclusive)
        end_date: End of period (inclusive)

    Returns:
        Sum of values for the period
    """
    result = db.query(func.sum(UsageStats.value)).filter(
        UsageStats.date >= start_date,
        UsageStats.date <= end_date,
        UsageStats.metric == metric
    ).scalar()

    return result or 0


def get_stats_summary(db: Session) -> dict:
    """
    Get a summary of all stats for the admin dashboard.

    Returns dict with:
    - today: dict of metric -> value for today
    - week: dict of metric -> total for last 7 days
    - month: dict of metric -> total for last 30 days
    - all_time: dict of metric -> total all time
    """
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Get all unique metrics
    metrics = db.query(UsageStats.metric).distinct().all()
    metric_names = [m[0] for m in metrics]

    result = {
        "today": {},
        "week": {},
        "month": {},
        "all_time": {},
    }

    for metric in metric_names:
        # Today
        today_stat = db.query(UsageStats).filter(
            UsageStats.date == today,
            UsageStats.metric == metric
        ).first()
        result["today"][metric] = today_stat.value if today_stat else 0

        # Last 7 days
        result["week"][metric] = get_total_for_period(db, metric, week_ago, today)

        # Last 30 days
        result["month"][metric] = get_total_for_period(db, metric, month_ago, today)

        # All time
        all_time = db.query(func.sum(UsageStats.value)).filter(
            UsageStats.metric == metric
        ).scalar()
        result["all_time"][metric] = all_time or 0

    return result


# Standard metric names
class Metrics:
    """Standard metric names for consistency."""
    ACTIVE_USERS_DAILY = "active_users_daily"
    LISTINGS_CREATED = "listings_created"
    LISTINGS_VIEWED = "listings_viewed"
    BUNDLES_CREATED = "bundles_created"
    DISCORD_COPIES = "discord_copies"
    FIO_SYNCS = "fio_syncs"
    LOGINS = "logins"
    PAGE_VIEWS = "page_views"
