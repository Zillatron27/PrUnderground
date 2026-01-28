#!/usr/bin/env python3
"""
Migration script to create the usage_stats table for telemetry tracking.

This script creates the 'usage_stats' table if it doesn't already exist.
The table stores anonymous daily counters for various metrics.

Usage:
    python scripts/add_usage_stats.py
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
    """Create usage_stats table if it doesn't exist."""
    if check_table_exists("usage_stats"):
        print("Table 'usage_stats' already exists. No migration needed.")
        return

    print("Creating 'usage_stats' table...")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                metric VARCHAR(50) NOT NULL,
                value INTEGER DEFAULT 0 NOT NULL,
                UNIQUE (date, metric)
            )
        """))

        # Create indexes for faster lookups
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_usage_stats_date ON usage_stats (date)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_usage_stats_metric ON usage_stats (metric)"
        ))

        conn.commit()

    print("Table 'usage_stats' created successfully!")
    print("\nUsage metrics will be tracked automatically.")
    print("View metrics at /admin/stats (requires ADMIN_USERNAMES env var)")


if __name__ == "__main__":
    main()
