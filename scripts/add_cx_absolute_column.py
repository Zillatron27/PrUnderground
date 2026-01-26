#!/usr/bin/env python3
"""
Migration script to add price_cx_is_absolute column to listings table.

This script adds the 'price_cx_is_absolute' column if it doesn't already exist.
The column defaults to False (percentage mode) for backwards compatibility.

Usage:
    python scripts/add_cx_absolute_column.py
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
    """Add price_cx_is_absolute column if it doesn't exist."""
    if check_column_exists("listings", "price_cx_is_absolute"):
        print("Column 'price_cx_is_absolute' already exists. No migration needed.")
        return

    print("Adding 'price_cx_is_absolute' column to listings table...")

    with engine.connect() as conn:
        conn.execute(
            text("ALTER TABLE listings ADD COLUMN price_cx_is_absolute BOOLEAN DEFAULT 0")
        )
        conn.commit()

    print("Column added successfully!")
    print("\nExisting CX-relative listings will use percentage mode (default).")


if __name__ == "__main__":
    main()
