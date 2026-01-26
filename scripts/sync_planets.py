#!/usr/bin/env python3
"""
Sync planets from FIO API to database.

Usage:
    python scripts/sync_planets.py         # Sync if needed (>30 days old or empty)
    python scripts/sync_planets.py --force # Force sync regardless of age
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import inspect
from app.database import engine, SessionLocal, Base
from app.models import Planet  # noqa: F401 - Import to register model
from app.services.planet_sync import sync_planets, is_planet_sync_needed


def check_table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


async def main():
    """Sync planets from FIO to database."""
    force = "--force" in sys.argv or "-f" in sys.argv

    # Ensure table exists
    if not check_table_exists("planets"):
        print("Creating 'planets' table...")
        Planet.__table__.create(engine)
        print("Created 'planets' table.")

    db = SessionLocal()
    try:
        if not force:
            if not is_planet_sync_needed(db):
                print("Planets are up to date (less than 30 days old). Use --force to sync anyway.")
                return

        print("Fetching planets from FIO API...")
        inserted, updated = await sync_planets(db, force=True)

        if inserted == 0 and updated == 0:
            print("No planets to sync (API returned empty)")
        else:
            print(f"Sync complete: {inserted} new planets, {updated} updated")

        # Show count
        count = db.query(Planet).count()
        print(f"Total planets in database: {count}")

        # Show some examples
        stations = db.query(Planet).filter(Planet.is_station == 1).all()
        print(f"CX Stations: {[s.name for s in stations]}")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
