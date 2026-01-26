"""
Planet Sync Service

Syncs planet/station data from FIO API to the database.
Planets rarely change in PrUn, so we only sync if:
- Table is empty
- Last sync was >30 days ago
- Manual sync is triggered
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import Planet
from ..fio_client import FIOClient

logger = logging.getLogger(__name__)

# How long before we consider planet data stale
# Planets can be renamed by players, so sync more frequently than materials
PLANET_TTL_DAYS = 14

# CX Station data (not in planet API, manually defined)
CX_STATION_DATA = [
    {"name": "Moria Station", "natural_id": "NC1", "system_name": "Hortus"},
    {"name": "Benten Station", "natural_id": "NC2", "system_name": "Benten"},
    {"name": "Hortus Station", "natural_id": "IC1", "system_name": "Hortus"},
    {"name": "Arclight Station", "natural_id": "CI1", "system_name": "Arclight"},
    {"name": "Antares Station", "natural_id": "AI1", "system_name": "Antares"},
]


def is_planet_sync_needed(db: Session, ttl_days: int = PLANET_TTL_DAYS) -> bool:
    """
    Check if planet sync is needed.

    Returns True if:
    - No planets in database
    - Most recent planet is older than ttl_days
    """
    count = db.query(func.count(Planet.id)).scalar()
    if count == 0:
        return True

    most_recent = db.query(func.max(Planet.updated_at)).scalar()
    if most_recent is None:
        return True

    age = datetime.utcnow() - most_recent
    return age > timedelta(days=ttl_days)


async def sync_planets(db: Session, force: bool = False) -> tuple[int, int]:
    """
    Fetch all planets from FIO and upsert to database.

    Args:
        db: Database session
        force: If True, sync even if not needed

    Returns:
        Tuple of (inserted_count, updated_count)
    """
    if not force and not is_planet_sync_needed(db):
        logger.info("Planet sync not needed (data is fresh)")
        return (0, 0)

    logger.info("Starting planet sync from FIO...")

    client = FIOClient()
    try:
        raw_planets = await client.get_all_planets()
    finally:
        await client.close()

    if not raw_planets:
        logger.warning("No planets returned from FIO API")
        return (0, 0)

    inserted = 0
    updated = 0
    now = datetime.utcnow()

    # Process planets from FIO
    for raw in raw_planets:
        # Use PlanetNaturalId as the unique key (e.g., "KW-688c")
        natural_id = raw.get("PlanetNaturalId")
        if not natural_id:
            continue

        name = raw.get("PlanetName") or natural_id

        existing = db.query(Planet).filter(Planet.planet_id == natural_id).first()

        if existing:
            existing.name = name
            existing.natural_id = natural_id
            existing.is_station = 0
            existing.updated_at = now
            updated += 1
        else:
            planet = Planet(
                planet_id=natural_id,
                name=name,
                natural_id=natural_id,
                system_name=None,
                is_station=0,
                updated_at=now,
            )
            db.add(planet)
            inserted += 1

    # Add CX stations (not in planet API)
    for station in CX_STATION_DATA:
        station_id = f"STATION_{station['natural_id']}"
        existing = db.query(Planet).filter(Planet.planet_id == station_id).first()

        if existing:
            existing.name = station["name"]
            existing.natural_id = station["natural_id"]
            existing.system_name = station["system_name"]
            existing.is_station = 1
            existing.updated_at = now
            updated += 1
        else:
            planet = Planet(
                planet_id=station_id,
                name=station["name"],
                natural_id=station["natural_id"],
                system_name=station["system_name"],
                is_station=1,
                updated_at=now,
            )
            db.add(planet)
            inserted += 1

    db.commit()
    logger.info(f"Planet sync complete: {inserted} inserted, {updated} updated")
    return (inserted, updated)


def get_all_locations_from_db(db: Session, query: Optional[str] = None) -> list[dict]:
    """
    Get all planets/stations from database for location picker.

    Args:
        db: Database session
        query: Optional search query (matches name or natural_id)

    Returns:
        List of location dicts sorted by: stations first, then alphabetically
    """
    q = db.query(Planet)

    if query:
        search = f"%{query}%"
        q = q.filter(
            (Planet.name.ilike(search)) | (Planet.natural_id.ilike(search))
        )

    # Sort: stations first, then by name
    planets = q.order_by(Planet.is_station.desc(), Planet.name).all()

    return [
        {
            "planet_id": p.planet_id,
            "name": p.name,
            "natural_id": p.natural_id,
            "system_name": p.system_name,
            "is_station": bool(p.is_station),
        }
        for p in planets
    ]


def get_cx_station_names(db: Session) -> set[str]:
    """
    Get the set of CX station names from the database.

    Used to identify which storage locations are CX stations.

    Returns:
        Set of station names (e.g., {"Moria Station", "Benten Station", ...})
    """
    stations = db.query(Planet.name).filter(Planet.is_station == 1).all()
    return {s.name for s in stations}
