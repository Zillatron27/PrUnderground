"""CX (Commodity Exchange) price synchronization service."""

import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..models import Exchange

logger = logging.getLogger(__name__)

# FIO API base URL
FIO_BASE_URL = "https://rest.fnar.net"


async def fetch_all_exchange_data() -> list[dict]:
    """
    Fetch all exchange data from FIO (all materials, all exchanges).

    Returns:
        List of exchange data dicts from FIO API
    """
    url = f"{FIO_BASE_URL}/exchange/all"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch exchange data: {e}")
            return []


async def sync_exchange_prices(db: Session) -> tuple[int, int]:
    """
    Sync all exchange prices from FIO to the database.

    Args:
        db: Database session

    Returns:
        Tuple of (inserted_count, updated_count)
    """
    inserted = 0
    updated = 0

    logger.info("Fetching all exchange data from FIO...")

    try:
        data = await fetch_all_exchange_data()

        if not data:
            logger.warning("No exchange data received from FIO")
            return 0, 0

        for item in data:
            ticker = item.get("MaterialTicker")
            exchange_code = item.get("ExchangeCode")

            if not ticker or not exchange_code:
                continue

            # Extract prices from FIO response
            price_ask = item.get("Ask")
            price_bid = item.get("Bid")
            price_average = item.get("PriceAverage")

            # Find existing record
            existing = db.query(Exchange).filter(
                Exchange.material_ticker == ticker,
                Exchange.exchange_code == exchange_code
            ).first()

            if existing:
                # Update existing record
                existing.price_ask = price_ask
                existing.price_bid = price_bid
                existing.price_average = price_average
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                # Insert new record
                exchange = Exchange(
                    material_ticker=ticker,
                    exchange_code=exchange_code,
                    price_ask=price_ask,
                    price_bid=price_bid,
                    price_average=price_average,
                )
                db.add(exchange)
                inserted += 1

        db.commit()
        logger.info(f"Exchange sync complete: {inserted} inserted, {updated} updated")

    except Exception as e:
        logger.error(f"Error syncing exchange data: {e}")
        db.rollback()

    return inserted, updated


def get_cx_price(db: Session, ticker: str, exchange_code: str) -> Optional[float]:
    """
    Get the CX ask price for a material at a specific exchange.

    Args:
        db: Database session
        ticker: Material ticker (e.g., "RAT")
        exchange_code: Exchange code (e.g., "NC1")

    Returns:
        The ask price or None if not found
    """
    exchange = db.query(Exchange).filter(
        Exchange.material_ticker == ticker,
        Exchange.exchange_code == exchange_code
    ).first()

    if exchange and exchange.price_ask:
        return exchange.price_ask
    return None


def get_cx_prices_bulk(db: Session) -> dict[tuple[str, str], float]:
    """
    Get all CX prices as a lookup dict.

    Args:
        db: Database session

    Returns:
        Dict mapping (ticker, exchange_code) to ask price
    """
    exchanges = db.query(Exchange).all()
    return {
        (e.material_ticker, e.exchange_code): e.price_ask
        for e in exchanges
        if e.price_ask is not None
    }


def get_last_sync_time(db: Session) -> Optional[datetime]:
    """
    Get the most recent exchange price update time.

    Args:
        db: Database session

    Returns:
        The most recent updated_at timestamp or None
    """
    latest = db.query(Exchange).order_by(Exchange.updated_at.desc()).first()
    return latest.updated_at if latest else None


def get_sync_age_string(db: Session) -> str:
    """
    Get a human-readable string for how old the CX data is.

    Args:
        db: Database session

    Returns:
        String like "5 minutes ago", "2 hours ago", etc.
    """
    last_sync = get_last_sync_time(db)
    if not last_sync:
        return "never synced"

    age = datetime.utcnow() - last_sync
    seconds = age.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    else:
        days = int(seconds / 86400)
        return f"{days}d ago"


def calculate_cx_price(
    base_price: float,
    offset: float,
    is_absolute: bool
) -> float:
    """
    Calculate the actual price from CX base + offset.

    Args:
        base_price: The CX ask price
        offset: The offset value (percentage or absolute)
        is_absolute: True for absolute offset, False for percentage

    Returns:
        The calculated price
    """
    if is_absolute:
        return base_price + offset
    else:
        # Percentage offset
        return base_price * (1 + offset / 100)
