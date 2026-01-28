#!/usr/bin/env python3
"""
Migration script to add discord_template column to users table.

This script adds the 'discord_template' column if it doesn't already exist.
The column is nullable - NULL means use the default template.

Usage:
    python scripts/add_discord_template.py
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
    """Add discord_template column to users table if it doesn't exist."""
    if check_column_exists("users", "discord_template"):
        print("Column 'discord_template' already exists in users table. No migration needed.")
        return

    print("Adding 'discord_template' column to users table...")

    with engine.connect() as conn:
        conn.execute(
            text("ALTER TABLE users ADD COLUMN discord_template TEXT DEFAULT NULL")
        )
        conn.commit()

    print("Column added successfully!")
    print("\nExisting users will use the default Discord template (NULL = default).")


if __name__ == "__main__":
    main()
