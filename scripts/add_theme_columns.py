#!/usr/bin/env python3
"""
Migration script to add theme preference columns to users table.

This script adds 'color_palette' and 'tile_style' columns if they don't already exist.
The columns are nullable - NULL means use the default/localStorage value.

Usage:
    python scripts/add_theme_columns.py
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
    """Add theme preference columns to users table if they don't exist."""
    added_any = False

    # Check and add color_palette column
    if check_column_exists("users", "color_palette"):
        print("Column 'color_palette' already exists in users table.")
    else:
        print("Adding 'color_palette' column to users table...")
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN color_palette VARCHAR(20) DEFAULT NULL")
            )
            conn.commit()
        print("Column 'color_palette' added successfully!")
        added_any = True

    # Check and add tile_style column
    if check_column_exists("users", "tile_style"):
        print("Column 'tile_style' already exists in users table.")
    else:
        print("Adding 'tile_style' column to users table...")
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN tile_style VARCHAR(20) DEFAULT NULL")
            )
            conn.commit()
        print("Column 'tile_style' added successfully!")
        added_any = True

    if added_any:
        print("\nExisting users will use localStorage values until they save preferences.")
    else:
        print("\nNo migration needed.")


if __name__ == "__main__":
    main()
