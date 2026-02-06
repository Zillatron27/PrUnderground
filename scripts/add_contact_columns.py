#!/usr/bin/env python3
"""
Migration script for v1.1.2: add contact information columns to users table.

Adds 'managing_director' and 'discord_username' columns if they don't already exist.
Both are nullable — empty means the user hasn't configured them yet.

Usage:
    python scripts/add_contact_columns.py
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
    """Add contact information columns to users table if they don't exist."""
    added_any = False

    # Check and add managing_director column
    if check_column_exists("users", "managing_director"):
        print("Column 'managing_director' already exists in users table.")
    else:
        print("Adding 'managing_director' column to users table...")
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN managing_director VARCHAR(100) DEFAULT NULL")
            )
            conn.commit()
        print("Column 'managing_director' added successfully!")
        added_any = True

    # Check and add discord_username column
    if check_column_exists("users", "discord_username"):
        print("Column 'discord_username' already exists in users table.")
    else:
        print("Adding 'discord_username' column to users table...")
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN discord_username VARCHAR(32) DEFAULT NULL")
            )
            conn.commit()
        print("Column 'discord_username' added successfully!")
        added_any = True

    if added_any:
        print("\nMigration complete. Users can set these fields in Account Settings.")
    else:
        print("\nNo migration needed.")


if __name__ == "__main__":
    main()
