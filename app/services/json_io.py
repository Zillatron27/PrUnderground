"""
JSON Import/Export module for PrUnderground.

Supports multiple data types with versioned schemas:
- prunderground-listings: User's listings only
- prunderground-backup: Full backup (profile + listings)

Future types can be added (e.g., rprun-action-package for RPrUn integration).
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy.orm import Session

from ..models import User, Listing, PriceType, ListingType


# Current schema version - increment when making breaking changes
SCHEMA_VERSION = "1.0"


class ImportMode(Enum):
    REPLACE = "replace"  # Delete all existing, import new
    MERGE_ADD = "merge_add"  # Only add listings for materials not already listed
    MERGE_UPDATE = "merge_update"  # Update existing + add new


class ImportResult:
    """Result of an import operation."""

    def __init__(self):
        self.success = True
        self.error: Optional[str] = None
        self.added = 0
        self.updated = 0
        self.skipped = 0
        self.deleted = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "error": self.error,
            "added": self.added,
            "updated": self.updated,
            "skipped": self.skipped,
            "deleted": self.deleted,
        }


# --- Export Functions ---


def export_listings(user: User) -> dict:
    """Export user's listings to JSON format."""
    listings_data = []
    for listing in user.listings:
        listings_data.append(_listing_to_dict(listing))

    return {
        "type": "prunderground-listings",
        "version": SCHEMA_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": {
            "fio_username": user.fio_username,
            "company_code": user.company_code,
        },
        "listings": listings_data,
    }


def export_backup(user: User) -> dict:
    """Export full user backup (profile + listings) to JSON format."""
    listings_data = []
    for listing in user.listings:
        listings_data.append(_listing_to_dict(listing))

    return {
        "type": "prunderground-backup",
        "version": SCHEMA_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": {
            "fio_username": user.fio_username,
            "company_code": user.company_code,
            "company_name": user.company_name,
            "discord_id": user.discord_id,
        },
        "listings": listings_data,
    }


def _listing_to_dict(listing: Listing) -> dict:
    """Convert a Listing model to a JSON-serializable dict."""
    return {
        "material_ticker": listing.material_ticker,
        "quantity": listing.quantity,
        "price_type": listing.price_type.value,
        "price_value": listing.price_value,
        "price_exchange": listing.price_exchange,
        "location": listing.location,
        "storage_id": listing.storage_id,
        "storage_name": listing.storage_name,
        "reserve_quantity": listing.reserve_quantity,
        "listing_type": listing.listing_type.value,
        "notes": listing.notes,
        "expires_at": listing.expires_at.isoformat() + "Z" if listing.expires_at else None,
    }


# --- Import Functions ---


def import_json(data: dict, user: User, db: Session, mode: ImportMode) -> ImportResult:
    """
    Import JSON data for a user.

    Routes to the appropriate handler based on the 'type' field.
    """
    result = ImportResult()

    if not isinstance(data, dict):
        result.success = False
        result.error = "Invalid JSON: expected an object"
        return result

    data_type = data.get("type")
    if not data_type:
        result.success = False
        result.error = "Missing 'type' field in JSON"
        return result

    # Route to appropriate handler
    match data_type:
        case "prunderground-listings":
            return _import_listings(data, user, db, mode)
        case "prunderground-backup":
            return _import_backup(data, user, db, mode)
        case _:
            result.success = False
            result.error = f"Unknown import type: {data_type}"
            return result


def _import_listings(data: dict, user: User, db: Session, mode: ImportMode) -> ImportResult:
    """Import listings from prunderground-listings format."""
    result = ImportResult()

    # Validate structure
    listings_data = data.get("listings")
    if not isinstance(listings_data, list):
        result.success = False
        result.error = "Missing or invalid 'listings' array"
        return result

    # Validate version compatibility
    version = data.get("version", "1.0")
    if not _is_version_compatible(version):
        result.success = False
        result.error = f"Incompatible schema version: {version}"
        return result

    # Process based on mode
    if mode == ImportMode.REPLACE:
        # Delete all existing listings
        result.deleted = len(user.listings)
        for listing in user.listings[:]:  # Copy list to avoid modification during iteration
            db.delete(listing)
        db.flush()

    # Get existing listings by material ticker for merge modes
    existing_by_ticker = {l.material_ticker: l for l in user.listings}

    for item in listings_data:
        ticker = item.get("material_ticker")
        if not ticker:
            result.skipped += 1
            continue

        if mode == ImportMode.MERGE_ADD and ticker in existing_by_ticker:
            # Skip if already exists
            result.skipped += 1
            continue

        if mode == ImportMode.MERGE_UPDATE and ticker in existing_by_ticker:
            # Update existing
            _update_listing_from_dict(existing_by_ticker[ticker], item)
            result.updated += 1
        else:
            # Create new listing
            listing = _dict_to_listing(item, user.id)
            if listing:
                db.add(listing)
                result.added += 1
            else:
                result.skipped += 1

    db.commit()
    return result


def _import_backup(data: dict, user: User, db: Session, mode: ImportMode) -> ImportResult:
    """Import full backup from prunderground-backup format."""
    result = ImportResult()

    # Validate version compatibility
    version = data.get("version", "1.0")
    if not _is_version_compatible(version):
        result.success = False
        result.error = f"Incompatible schema version: {version}"
        return result

    # Update user profile data (non-credential fields only)
    user_data = data.get("user", {})
    if user_data.get("company_name"):
        user.company_name = user_data["company_name"]
    if user_data.get("discord_id"):
        user.discord_id = user_data["discord_id"]
    # Note: company_code comes from FIO, so we don't overwrite it

    # Import listings using the same logic
    listings_data = data.get("listings", [])
    data_with_listings = {"listings": listings_data, "version": version}
    listings_result = _import_listings(data_with_listings, user, db, mode)

    # Combine results
    result.added = listings_result.added
    result.updated = listings_result.updated
    result.skipped = listings_result.skipped
    result.deleted = listings_result.deleted
    result.success = listings_result.success
    result.error = listings_result.error

    return result


def _dict_to_listing(data: dict, user_id: int) -> Optional[Listing]:
    """Convert a dict to a Listing model. Returns None if invalid."""
    ticker = data.get("material_ticker")
    if not ticker:
        return None

    # Parse price_type
    try:
        price_type = PriceType(data.get("price_type", "contact_me"))
    except ValueError:
        price_type = PriceType.CONTACT_ME

    # Parse listing_type
    try:
        listing_type = ListingType(data.get("listing_type", "standing"))
    except ValueError:
        listing_type = ListingType.STANDING

    # Parse expires_at
    expires_at = None
    if data.get("expires_at"):
        try:
            expires_str = data["expires_at"].replace("Z", "+00:00")
            expires_at = datetime.fromisoformat(expires_str).replace(tzinfo=None)
        except (ValueError, AttributeError):
            pass

    return Listing(
        user_id=user_id,
        material_ticker=ticker.upper(),
        quantity=data.get("quantity"),
        price_type=price_type,
        price_value=data.get("price_value"),
        price_exchange=data.get("price_exchange"),
        location=data.get("location"),
        storage_id=data.get("storage_id"),
        storage_name=data.get("storage_name"),
        reserve_quantity=data.get("reserve_quantity", 0),
        listing_type=listing_type,
        notes=data.get("notes"),
        expires_at=expires_at,
    )


def _update_listing_from_dict(listing: Listing, data: dict) -> None:
    """Update an existing listing from dict data."""
    if "quantity" in data:
        listing.quantity = data["quantity"]

    if "price_type" in data:
        try:
            listing.price_type = PriceType(data["price_type"])
        except ValueError:
            pass

    if "price_value" in data:
        listing.price_value = data["price_value"]

    if "price_exchange" in data:
        listing.price_exchange = data["price_exchange"]

    if "location" in data:
        listing.location = data["location"]

    if "storage_id" in data:
        listing.storage_id = data["storage_id"]

    if "storage_name" in data:
        listing.storage_name = data["storage_name"]

    if "reserve_quantity" in data:
        listing.reserve_quantity = data["reserve_quantity"]

    if "listing_type" in data:
        try:
            listing.listing_type = ListingType(data["listing_type"])
        except ValueError:
            pass

    if "notes" in data:
        listing.notes = data["notes"]

    if "expires_at" in data:
        if data["expires_at"]:
            try:
                expires_str = data["expires_at"].replace("Z", "+00:00")
                listing.expires_at = datetime.fromisoformat(expires_str).replace(tzinfo=None)
            except (ValueError, AttributeError):
                pass
        else:
            listing.expires_at = None

    listing.updated_at = datetime.utcnow()


def _is_version_compatible(version: str) -> bool:
    """Check if a schema version is compatible with current version."""
    # For now, we only support 1.x versions
    try:
        major = int(version.split(".")[0])
        return major == 1
    except (ValueError, IndexError):
        return False


# --- Utility Functions ---


def get_export_filename(export_type: str, username: str) -> str:
    """Generate a filename for an export."""
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{export_type}-{username}-{timestamp}.json"
