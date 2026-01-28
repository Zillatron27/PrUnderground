"""
FIO Data Sync Service

Single responsibility: Sync FIO data for a user and update their listings in DB.
Views never call FIO directly - they only read from DB.
"""

import logging
from datetime import datetime
from sqlalchemy.orm import Session

from ..models import User, Listing, Bundle, BundleStockMode
from ..fio_client import FIOClient, extract_storage_locations
from ..encryption import decrypt_api_key
from .planet_sync import get_cx_station_names

logger = logging.getLogger(__name__)


def is_sync_needed(user: User, ttl_seconds: int = 600) -> bool:
    """Check if FIO sync is needed (never synced or TTL expired)."""
    if not user.fio_last_synced:
        return True
    age = datetime.utcnow() - user.fio_last_synced
    return age.total_seconds() > ttl_seconds


async def sync_user_fio_data(user: User, db: Session, force: bool = False) -> bool:
    """
    Fetch fresh FIO data for ONE user and update their listings in DB.

    Only syncs if force=True OR is_sync_needed() returns True.

    Updates:
    - This user's listings with current available_quantity
    - user.fio_last_synced timestamp

    Returns True if successful (or no sync needed), False if sync failed.
    """
    if not force and not is_sync_needed(user):
        return True  # Data is fresh, no sync needed

    if not user.fio_api_key:
        logger.warning(f"Cannot sync FIO data for {user.fio_username}: no API key")
        return False

    # Decrypt the API key before use
    decrypted_key = decrypt_api_key(user.fio_api_key)
    client = FIOClient(api_key=decrypted_key)

    try:
        # Fetch FIO data
        raw_storages = await client.get_user_storage(user.fio_username)
        sites = await client.get_user_sites(user.fio_username)
        warehouses = await client.get_user_warehouses(user.fio_username)

        # Get CX station names from database for is_cx identification
        cx_station_names = get_cx_station_names(db)

        # Process into storage locations with inventory
        storage_locations = extract_storage_locations(
            raw_storages, sites, warehouses, cx_station_names
        )

        # Build inventory map: storage_id -> {material_ticker -> amount}
        storage_inventory = {}
        for storage in storage_locations:
            storage_inventory[storage["addressable_id"]] = storage["items"]

        # Update this user's listings
        user_listings = db.query(Listing).filter(Listing.user_id == user.id).all()

        for listing in user_listings:
            if listing.storage_id and listing.storage_id in storage_inventory:
                items = storage_inventory[listing.storage_id]
                actual = items.get(listing.material_ticker, 0)
                reserve = listing.reserve_quantity or 0
                listing.available_quantity = max(0, actual - reserve)
            # If no storage linked or storage not found, keep existing value
            # (stale data is better than no data)

        # Update FIO_SYNC bundles
        user_bundles = db.query(Bundle).filter(
            Bundle.user_id == user.id,
            Bundle.stock_mode == BundleStockMode.FIO_SYNC
        ).all()

        for bundle in user_bundles:
            if bundle.storage_id and bundle.storage_id in storage_inventory:
                items = storage_inventory[bundle.storage_id]
                available = None
                for bundle_item in bundle.items:
                    stock = items.get(bundle_item.material_ticker, 0)
                    can_make = stock // bundle_item.quantity if bundle_item.quantity > 0 else 0
                    if available is None or can_make < available:
                        available = can_make
                bundle.available_quantity = available if available is not None else 0
            # If no storage linked or storage not found, keep existing value

        # Update sync timestamp
        user.fio_last_synced = datetime.utcnow()

        db.commit()
        logger.info(f"FIO sync complete for {user.fio_username}: {len(user_listings)} listings updated")
        return True

    except Exception as e:
        logger.error(f"FIO sync failed for {user.fio_username}: {e}")
        return False
    finally:
        await client.close()


def get_sync_staleness(user: User) -> str:
    """
    Get human-readable staleness string for user's FIO data.
    Returns e.g., "just now", "5m ago", "2h ago", "yesterday", "3 days ago"
    """
    if not user.fio_last_synced:
        return "never"

    now = datetime.utcnow()
    delta = now - user.fio_last_synced
    seconds = delta.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    elif seconds < 172800:
        return "yesterday"
    else:
        days = int(seconds / 86400)
        return f"{days} days ago"
