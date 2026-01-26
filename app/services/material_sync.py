"""
Material Sync Service

Syncs material data from FIO API to the database.
Materials rarely change in PrUn, so we only sync if:
- Table is empty
- Last sync was >30 days ago
- Manual sync is triggered
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import Material
from ..fio_client import FIOClient

logger = logging.getLogger(__name__)

# How long before we consider material data stale
MATERIAL_TTL_DAYS = 30


def format_material_name(name: str) -> str:
    """Convert CamelCase to Title Case with spaces (e.g., 'HullComponent' -> 'Hull Component')."""
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    return spaced.title()


def is_material_sync_needed(db: Session, ttl_days: int = MATERIAL_TTL_DAYS) -> bool:
    """
    Check if material sync is needed.

    Returns True if:
    - No materials in database
    - Most recent material is older than ttl_days
    """
    # Check if any materials exist
    count = db.query(func.count(Material.id)).scalar()
    if count == 0:
        return True

    # Check the most recent update
    most_recent = db.query(func.max(Material.updated_at)).scalar()
    if most_recent is None:
        return True

    age = datetime.utcnow() - most_recent
    return age > timedelta(days=ttl_days)


async def sync_materials(db: Session, force: bool = False) -> tuple[int, int]:
    """
    Fetch all materials from FIO and upsert to database.

    Args:
        db: Database session
        force: If True, sync even if not needed

    Returns:
        Tuple of (inserted_count, updated_count)
    """
    if not force and not is_material_sync_needed(db):
        logger.info("Material sync not needed (data is fresh)")
        return (0, 0)

    logger.info("Starting material sync from FIO...")

    client = FIOClient()
    try:
        raw_materials = await client.get_all_materials()
    finally:
        await client.close()

    if not raw_materials:
        logger.warning("No materials returned from FIO API")
        return (0, 0)

    inserted = 0
    updated = 0
    now = datetime.utcnow()

    for raw in raw_materials:
        ticker = raw.get("Ticker")
        if not ticker:
            continue

        # Check if material exists
        existing = db.query(Material).filter(Material.ticker == ticker).first()

        if existing:
            # Update existing
            existing.name = format_material_name(raw.get("Name", ticker))
            existing.category_name = raw.get("CategoryName")
            existing.category_id = raw.get("CategoryId")
            existing.weight = raw.get("Weight")
            existing.volume = raw.get("Volume")
            existing.updated_at = now
            updated += 1
        else:
            # Insert new
            material = Material(
                ticker=ticker,
                name=format_material_name(raw.get("Name", ticker)),
                category_name=raw.get("CategoryName"),
                category_id=raw.get("CategoryId"),
                weight=raw.get("Weight"),
                volume=raw.get("Volume"),
                updated_at=now,
            )
            db.add(material)
            inserted += 1

    db.commit()
    logger.info(f"Material sync complete: {inserted} inserted, {updated} updated")
    return (inserted, updated)


def get_all_materials_from_db(db: Session, category: Optional[str] = None) -> list[dict]:
    """
    Get all materials from database.

    Args:
        db: Database session
        category: Optional category filter (case-insensitive partial match)

    Returns:
        List of material dicts sorted by ticker
    """
    query = db.query(Material)

    if category:
        query = query.filter(Material.category_name.ilike(f"%{category}%"))

    materials = query.order_by(Material.ticker).all()

    return [
        {
            "ticker": m.ticker,
            "name": m.name,
            "category_name": m.category_name,
            "category_id": m.category_id,
            "weight": m.weight,
            "volume": m.volume,
        }
        for m in materials
    ]


def get_material_categories(db: Session) -> list[str]:
    """Get list of unique category names from materials table."""
    categories = (
        db.query(Material.category_name)
        .filter(Material.category_name.isnot(None))
        .distinct()
        .order_by(Material.category_name)
        .all()
    )
    return [c[0] for c in categories]
