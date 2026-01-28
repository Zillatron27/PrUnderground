#!/usr/bin/env python3
"""
Migration script to add low_stock_threshold column to listings and bundles tables.

This script adds the 'low_stock_threshold' column if it doesn't already exist.
- For listings: defaults to 10 (existing behavior preserved)
- For bundles: defaults to NULL (no threshold check)

Usage:
    python scripts/add_low_stock_threshold.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from app.database import engine


def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def main():
    """Add low_stock_threshold column to listings and bundles if it doesn't exist."""
    changes_made = False

    # Add to listings table
    if check_column_exists("listings", "low_stock_threshold"):
        print("Column 'low_stock_threshold' already exists in listings table.")
    else:
        print("Adding 'low_stock_threshold' column to listings table...")
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE listings ADD COLUMN low_stock_threshold INTEGER DEFAULT 10")
            )
            conn.commit()
        print("Column added to listings table successfully!")
        changes_made = True

    # Add to bundles table
    if check_column_exists("bundles", "low_stock_threshold"):
        print("Column 'low_stock_threshold' already exists in bundles table.")
    else:
        print("Adding 'low_stock_threshold' column to bundles table...")
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE bundles ADD COLUMN low_stock_threshold INTEGER DEFAULT NULL")
            )
            conn.commit()
        print("Column added to bundles table successfully!")
        changes_made = True

    if changes_made:
        print("\nMigration complete!")
        print("- Listings: default threshold is 10 (existing behavior preserved)")
        print("- Bundles: default threshold is NULL (no low stock check)")
    else:
        print("\nNo migration needed - columns already exist.")


if __name__ == "__main__":
    main()
