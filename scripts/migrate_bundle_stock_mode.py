#!/usr/bin/env python3
"""
Migration script to add bundle stock mode columns.

This script adds the following columns to the 'bundles' table:
- stock_mode (VARCHAR, default 'manual')
- storage_id (VARCHAR, nullable)
- storage_name (VARCHAR, nullable)
- available_quantity (INTEGER, nullable)
- ready_quantity (INTEGER, nullable)

Usage:
    python scripts/migrate_bundle_stock_mode.py

Note: If you're starting fresh, the columns will be created automatically by
Base.metadata.create_all() in main.py when the app starts.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from app.database import engine


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def main():
    """Add stock mode columns to bundles table if they don't exist."""
    columns_to_add = [
        ("stock_mode", "VARCHAR(20) DEFAULT 'MANUAL' NOT NULL"),
        ("storage_id", "VARCHAR(100)"),
        ("storage_name", "VARCHAR(100)"),
        ("available_quantity", "INTEGER"),
        ("ready_quantity", "INTEGER"),
    ]

    added = []
    skipped = []

    with engine.connect() as conn:
        for col_name, col_def in columns_to_add:
            if column_exists("bundles", col_name):
                skipped.append(col_name)
            else:
                print(f"Adding column '{col_name}' to bundles table...")
                conn.execute(text(f"ALTER TABLE bundles ADD COLUMN {col_name} {col_def}"))
                added.append(col_name)

        conn.commit()

    if added:
        print(f"\nAdded columns: {', '.join(added)}")
    if skipped:
        print(f"Skipped (already exist): {', '.join(skipped)}")

    if not added:
        print("\nNo migration needed - all columns already exist.")
    else:
        print("\nMigration complete! Bundle stock modes are now available.")


if __name__ == "__main__":
    main()
