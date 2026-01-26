#!/usr/bin/env python3
"""
Migration script to add bundle tables.

This script adds the 'bundles' and 'bundle_items' tables if they don't already exist.
Run this script if you have an existing database that needs the new bundle feature.

Usage:
    python scripts/add_bundle_tables.py

Note: If you're starting fresh, the tables will be created automatically by
Base.metadata.create_all() in main.py when the app starts.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect
from app.database import engine, Base
from app.models import Bundle, BundleItem  # noqa: F401 - Import to register models


def check_table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def main():
    """Add bundle tables if they don't exist."""
    bundles_exists = check_table_exists("bundles")
    bundle_items_exists = check_table_exists("bundle_items")

    if bundles_exists and bundle_items_exists:
        print("Bundle tables already exist. No migration needed.")
        return

    if not bundles_exists:
        print("Creating 'bundles' table...")
        Bundle.__table__.create(engine)
        print("Created 'bundles' table.")

    if not bundle_items_exists:
        print("Creating 'bundle_items' table...")
        BundleItem.__table__.create(engine)
        print("Created 'bundle_items' table.")

    print("\nMigration complete! Bundle feature is now available.")


if __name__ == "__main__":
    main()
