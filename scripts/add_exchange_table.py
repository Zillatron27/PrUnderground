#!/usr/bin/env python3
"""
Migration script to create the exchanges table for CX price caching.

This script creates the 'exchanges' table if it doesn't already exist.
The table stores cached commodity exchange prices from FIO.

Usage:
    python scripts/add_exchange_table.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from app.database import engine


def check_table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def main():
    """Create exchanges table if it doesn't exist."""
    if check_table_exists("exchanges"):
        print("Table 'exchanges' already exists. No migration needed.")
        return

    print("Creating 'exchanges' table...")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE exchanges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_ticker VARCHAR(10) NOT NULL,
                exchange_code VARCHAR(10) NOT NULL,
                price_ask FLOAT,
                price_bid FLOAT,
                price_average FLOAT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (material_ticker, exchange_code)
            )
        """))

        # Create indexes for faster lookups
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_exchanges_material_ticker ON exchanges (material_ticker)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_exchanges_exchange_code ON exchanges (exchange_code)"
        ))

        conn.commit()

    print("Table 'exchanges' created successfully!")
    print("\nCX prices will be synced automatically by the background scheduler.")
    print("First sync will happen on app startup.")


if __name__ == "__main__":
    main()
