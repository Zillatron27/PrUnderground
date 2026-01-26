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

from ..models import User, Listing, Bundle, BundleItem, PriceType, ListingType


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


def export_bundles(user: User) -> dict:
    """Export user's bundles to JSON format."""
    bundles_data = []
    for bundle in user.bundles:
        bundles_data.append(_bundle_to_dict(bundle))

    return {
        "type": "prunderground-bundles",
        "version": SCHEMA_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": {
            "fio_username": user.fio_username,
            "company_code": user.company_code,
        },
        "bundles": bundles_data,
    }


def export_backup(user: User) -> dict:
    """Export full user backup (profile + listings + bundles) to JSON format."""
    listings_data = []
    for listing in user.listings:
        listings_data.append(_listing_to_dict(listing))

    bundles_data = []
    for bundle in user.bundles:
        bundles_data.append(_bundle_to_dict(bundle))

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
        "bundles": bundles_data,
    }


def _listing_to_dict(listing: Listing) -> dict:
    """Convert a Listing model to a JSON-serializable dict."""
    return {
        "material_ticker": listing.material_ticker,
        "quantity": listing.quantity,
        "price_type": listing.price_type.value,
        "price_value": listing.price_value,
        "price_exchange": listing.price_exchange,
        "price_cx_is_absolute": listing.price_cx_is_absolute or False,
        "location": listing.location,
        "storage_id": listing.storage_id,
        "storage_name": listing.storage_name,
        "reserve_quantity": listing.reserve_quantity,
        "listing_type": listing.listing_type.value,
        "notes": listing.notes,
        "expires_at": listing.expires_at.isoformat() + "Z" if listing.expires_at else None,
    }


def _bundle_to_dict(bundle: Bundle) -> dict:
    """Convert a Bundle model to a JSON-serializable dict."""
    items = []
    for item in bundle.items:
        items.append({
            "material_ticker": item.material_ticker,
            "quantity": item.quantity,
        })

    return {
        "name": bundle.name,
        "description": bundle.description,
        "quantity": bundle.quantity,
        "price": bundle.price,
        "currency": bundle.currency,
        "location": bundle.location,
        "listing_type": bundle.listing_type.value,
        "notes": bundle.notes,
        "expires_at": bundle.expires_at.isoformat() + "Z" if bundle.expires_at else None,
        "items": items,
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
        case "prunderground-bundles":
            return _import_bundles(data, user, db, mode)
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


def _import_bundles(data: dict, user: User, db: Session, mode: ImportMode) -> ImportResult:
    """Import bundles from prunderground-bundles format."""
    result = ImportResult()

    # Validate structure
    bundles_data = data.get("bundles")
    if not isinstance(bundles_data, list):
        result.success = False
        result.error = "Missing or invalid 'bundles' array"
        return result

    # Validate version compatibility
    version = data.get("version", "1.0")
    if not _is_version_compatible(version):
        result.success = False
        result.error = f"Incompatible schema version: {version}"
        return result

    # Process based on mode
    if mode == ImportMode.REPLACE:
        # Delete all existing bundles
        result.deleted = len(user.bundles)
        for bundle in user.bundles[:]:
            db.delete(bundle)
        db.flush()

    # Get existing bundles by name for merge modes
    existing_by_name = {b.name: b for b in user.bundles}

    for item in bundles_data:
        name = item.get("name")
        if not name:
            result.skipped += 1
            continue

        if mode == ImportMode.MERGE_ADD and name in existing_by_name:
            result.skipped += 1
            continue

        if mode == ImportMode.MERGE_UPDATE and name in existing_by_name:
            _update_bundle_from_dict(existing_by_name[name], item, db)
            result.updated += 1
        else:
            bundle = _dict_to_bundle(item, user.id, db)
            if bundle:
                db.add(bundle)
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

    # Import bundles using the same logic
    bundles_data = data.get("bundles", [])
    data_with_bundles = {"bundles": bundles_data, "version": version}
    bundles_result = _import_bundles(data_with_bundles, user, db, mode)

    # Combine results
    result.added = listings_result.added + bundles_result.added
    result.updated = listings_result.updated + bundles_result.updated
    result.skipped = listings_result.skipped + bundles_result.skipped
    result.deleted = listings_result.deleted + bundles_result.deleted
    result.success = listings_result.success and bundles_result.success
    if listings_result.error:
        result.error = listings_result.error
    elif bundles_result.error:
        result.error = bundles_result.error

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
        price_cx_is_absolute=data.get("price_cx_is_absolute", False),
        location=data.get("location"),
        storage_id=data.get("storage_id"),
        storage_name=data.get("storage_name"),
        reserve_quantity=data.get("reserve_quantity", 0),
        listing_type=listing_type,
        notes=data.get("notes"),
        expires_at=expires_at,
    )


def _dict_to_bundle(data: dict, user_id: int, db: Session) -> Optional[Bundle]:
    """Convert a dict to a Bundle model. Returns None if invalid."""
    name = data.get("name")
    if not name:
        return None

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

    bundle = Bundle(
        user_id=user_id,
        name=name,
        description=data.get("description"),
        quantity=data.get("quantity"),
        price=data.get("price"),
        currency=data.get("currency"),
        location=data.get("location"),
        listing_type=listing_type,
        notes=data.get("notes"),
        expires_at=expires_at,
    )

    # Add bundle items
    items_data = data.get("items", [])
    for item_data in items_data:
        ticker = item_data.get("material_ticker")
        if ticker:
            item = BundleItem(
                material_ticker=ticker.upper(),
                quantity=item_data.get("quantity", 1),
            )
            bundle.items.append(item)

    return bundle


def _update_bundle_from_dict(bundle: Bundle, data: dict, db: Session) -> None:
    """Update an existing bundle from dict data."""
    if "description" in data:
        bundle.description = data["description"]

    if "quantity" in data:
        bundle.quantity = data["quantity"]

    if "price" in data:
        bundle.price = data["price"]

    if "currency" in data:
        bundle.currency = data["currency"]

    if "location" in data:
        bundle.location = data["location"]

    if "listing_type" in data:
        try:
            bundle.listing_type = ListingType(data["listing_type"])
        except ValueError:
            pass

    if "notes" in data:
        bundle.notes = data["notes"]

    if "expires_at" in data:
        if data["expires_at"]:
            try:
                expires_str = data["expires_at"].replace("Z", "+00:00")
                bundle.expires_at = datetime.fromisoformat(expires_str).replace(tzinfo=None)
            except (ValueError, AttributeError):
                pass
        else:
            bundle.expires_at = None

    # Replace all items if provided
    if "items" in data:
        for old_item in bundle.items[:]:
            db.delete(old_item)

        for item_data in data["items"]:
            ticker = item_data.get("material_ticker")
            if ticker:
                item = BundleItem(
                    bundle_id=bundle.id,
                    material_ticker=ticker.upper(),
                    quantity=item_data.get("quantity", 1),
                )
                db.add(item)

    bundle.updated_at = datetime.utcnow()


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

    if "price_cx_is_absolute" in data:
        listing.price_cx_is_absolute = data["price_cx_is_absolute"]

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
