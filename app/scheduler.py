"""Background scheduler for periodic tasks."""

import logging
import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


async def sync_exchange_prices_job():
    """Job to sync CX prices from FIO."""
    from .database import SessionLocal
    from .services.cx_sync import sync_exchange_prices

    logger.info("Starting scheduled CX price sync...")
    db = SessionLocal()
    try:
        inserted, updated = await sync_exchange_prices(db)
        logger.info(f"Scheduled CX sync complete: {inserted} new, {updated} updated")
    except Exception as e:
        logger.error(f"Scheduled CX sync failed: {e}")
    finally:
        db.close()


def get_scheduler() -> AsyncIOScheduler:
    """Get the global scheduler instance, creating it if needed."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler():
    """Start the background scheduler with all configured jobs."""
    scheduler = get_scheduler()

    # Don't start if already running
    if scheduler.running:
        logger.info("Scheduler already running")
        return

    # Add CX price sync job - runs every 30 minutes
    scheduler.add_job(
        sync_exchange_prices_job,
        trigger=IntervalTrigger(minutes=30),
        id="cx_price_sync",
        name="CX Price Sync",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Background scheduler started")

    # Run initial sync immediately in background
    asyncio.create_task(sync_exchange_prices_job())


def stop_scheduler():
    """Stop the background scheduler gracefully."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
    _scheduler = None
