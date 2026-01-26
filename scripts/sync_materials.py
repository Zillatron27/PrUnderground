#!/usr/bin/env python3
"""
Sync materials from FIO API to database.

Usage:
    python scripts/sync_materials.py         # Sync if needed (>30 days old or empty)
    python scripts/sync_materials.py --force # Force sync regardless of age
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
from app.models import Material  # noqa: F401 - Import to register model
from app.services.material_sync import sync_materials, is_material_sync_needed


def check_table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


async def main():
    """Sync materials from FIO to database."""
    force = "--force" in sys.argv or "-f" in sys.argv

    # Ensure table exists
    if not check_table_exists("materials"):
        print("Creating 'materials' table...")
        Material.__table__.create(engine)
        print("Created 'materials' table.")

    db = SessionLocal()
    try:
        if not force:
            if not is_material_sync_needed(db):
                print("Materials are up to date (less than 30 days old). Use --force to sync anyway.")
                return

        print("Fetching materials from FIO API...")
        inserted, updated = await sync_materials(db, force=True)

        if inserted == 0 and updated == 0:
            print("No materials to sync (API returned empty)")
        else:
            print(f"Sync complete: {inserted} new materials, {updated} updated")

        # Show count
        count = db.query(Material).count()
        print(f"Total materials in database: {count}")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
