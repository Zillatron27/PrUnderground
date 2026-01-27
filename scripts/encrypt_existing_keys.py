#!/usr/bin/env python3
"""
One-time migration script to encrypt existing plaintext FIO API keys.

Run this ONCE after deploying the encryption feature.
Safe to run multiple times - already-encrypted keys are skipped.

Usage:
    python scripts/encrypt_existing_keys.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models import User
from app.encryption import encrypt_api_key, decrypt_api_key


def is_already_encrypted(key: str) -> bool:
    """
    Check if a key appears to already be encrypted.

    Fernet tokens start with 'gAAAAA' (base64-encoded version byte).
    Plaintext FIO API keys are typically alphanumeric UUIDs.
    """
    if not key:
        return False
    # Fernet tokens always start with 'gAAAAA'
    return key.startswith("gAAAAA")


def migrate_keys():
    """Encrypt all plaintext FIO API keys in the database."""
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.fio_api_key.isnot(None)).all()

        migrated = 0
        skipped = 0
        errors = 0

        for user in users:
            if not user.fio_api_key:
                continue

            if is_already_encrypted(user.fio_api_key):
                skipped += 1
                continue

            try:
                # Encrypt the plaintext key
                encrypted = encrypt_api_key(user.fio_api_key)
                user.fio_api_key = encrypted
                migrated += 1
            except Exception as e:
                print(f"Error encrypting key for user {user.fio_username}: {e}")
                errors += 1

        db.commit()
        print(f"Migration complete:")
        print(f"  - Migrated: {migrated}")
        print(f"  - Skipped (already encrypted): {skipped}")
        print(f"  - Errors: {errors}")

    finally:
        db.close()


if __name__ == "__main__":
    print("Encrypting existing FIO API keys...")
    migrate_keys()
