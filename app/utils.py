"""Shared utility functions."""

from typing import Optional

from .models import PriceType


def clean_str(val: Optional[str]) -> Optional[str]:
    """Sanitize optional string fields - empty strings and 'None' become None."""
    if not val or val.strip() == "" or val.strip().lower() == "none":
        return None
    return val.strip()


def format_price(listing) -> str:
    """Format a listing's price for display."""
    if listing.price_type == PriceType.ABSOLUTE:
        return f"{listing.price_value:,.0f}/u" if listing.price_value else "Contact me"
    elif listing.price_type == PriceType.CX_RELATIVE:
        if listing.price_value is None:
            return "CX price"
        sign = "+" if listing.price_value >= 0 else ""
        exchange = f".{listing.price_exchange}" if listing.price_exchange else ""
        return f"CX{exchange}{sign}{listing.price_value:.0f}%"
    else:
        return "Contact me"
