"""Shared utility functions."""

from datetime import datetime
from typing import Optional

from .models import PriceType


def clean_str(val: Optional[str]) -> Optional[str]:
    """Sanitize optional string fields - empty strings and 'None' become None."""
    if not val or val.strip() == "" or val.strip().lower() == "none":
        return None
    return val.strip()


def format_price(listing, cx_prices: dict = None) -> str:
    """
    Format a listing's price for display.

    Args:
        listing: The listing object
        cx_prices: Optional dict mapping (ticker, exchange_code) to CX ask price.
                   If provided and listing is CX-relative, shows calculated price.

    Returns:
        Formatted price string
    """
    if listing.price_type == PriceType.ABSOLUTE:
        return f"{listing.price_value:,.0f}/u" if listing.price_value else "Contact me"
    elif listing.price_type == PriceType.CX_RELATIVE:
        if listing.price_value is None:
            return "CX price"
        sign = "+" if listing.price_value >= 0 else ""
        exchange = f".{listing.price_exchange}" if listing.price_exchange else ""
        if getattr(listing, 'price_cx_is_absolute', False):
            base_str = f"CX{exchange}{sign}{listing.price_value:,.0f}"
        else:
            base_str = f"CX{exchange}{sign}{listing.price_value:.0f}%"

        # If we have CX prices, calculate and append the actual price
        if cx_prices and listing.price_exchange and listing.material_ticker:
            cx_key = (listing.material_ticker, listing.price_exchange)
            cx_ask = cx_prices.get(cx_key)
            if cx_ask:
                calculated = calculate_cx_actual_price(
                    cx_ask, listing.price_value, listing.price_cx_is_absolute
                )
                return f"{base_str} ({calculated:,.0f}/u)"

        return base_str
    else:
        return "Contact me"


def calculate_cx_actual_price(cx_ask: float, offset: float, is_absolute: bool) -> float:
    """
    Calculate the actual price from CX ask + offset.

    Args:
        cx_ask: The CX ask price
        offset: The offset value (percentage or absolute)
        is_absolute: True for absolute offset, False for percentage

    Returns:
        The calculated price
    """
    if is_absolute:
        return cx_ask + offset
    else:
        return cx_ask * (1 + offset / 100)


def get_stock_status(listing) -> Optional[str]:
    """
    Get stock status from listing's stored available_quantity.
    Uses listing's low_stock_threshold if set, otherwise defaults to 10.
    Returns 'out', 'low', or None (ok/no data).
    """
    if listing.available_quantity is None:
        return None
    if listing.available_quantity == 0:
        return "out"
    threshold = listing.low_stock_threshold if listing.low_stock_threshold is not None else 10
    if listing.available_quantity <= threshold:
        return "low"
    return None


def get_bundle_stock_status(bundle) -> Optional[str]:
    """
    Get stock status for a bundle based on its stock mode and threshold.
    Returns 'out', 'low', or None (ok/no data/no threshold).

    If low_stock_threshold is None, no low stock check is performed.
    """
    from .models import BundleStockMode

    # No threshold set means no stock checking
    if bundle.low_stock_threshold is None:
        # Still check for out-of-stock in applicable modes
        if bundle.stock_mode == BundleStockMode.MANUAL:
            if bundle.quantity is not None and bundle.quantity == 0:
                return "out"
        elif bundle.stock_mode == BundleStockMode.FIO_SYNC:
            if bundle.available_quantity is not None and bundle.available_quantity == 0:
                return "out"
        return None

    # Get the relevant quantity based on stock mode
    qty = None
    if bundle.stock_mode == BundleStockMode.MANUAL:
        qty = bundle.quantity
    elif bundle.stock_mode == BundleStockMode.FIO_SYNC:
        qty = bundle.available_quantity
    elif bundle.stock_mode in (BundleStockMode.UNLIMITED, BundleStockMode.MADE_TO_ORDER):
        # These modes don't have stock limits
        return None

    if qty is None:
        return None
    if qty == 0:
        return "out"
    if qty <= bundle.low_stock_threshold:
        return "low"
    return None


def is_sync_stale(user, hours: int = 24) -> bool:
    """Check if user's FIO sync is older than specified hours."""
    if not user or not user.fio_last_synced:
        return True
    age = datetime.utcnow() - user.fio_last_synced
    return age.total_seconds() > (hours * 3600)
