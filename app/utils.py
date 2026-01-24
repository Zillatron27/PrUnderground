"""Shared utility functions."""

from .models import PriceType


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
