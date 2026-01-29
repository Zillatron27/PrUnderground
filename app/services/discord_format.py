"""Discord formatting service for customizable copy/paste text."""

import re
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import User, Listing

# Default template that matches the original format
DEFAULT_TEMPLATE = """🚀 **[{company_code}] {username}** - Updated {date}

{listings_by_location}

📋 Full listings: {profile_url}"""

# Template for each location section
LOCATION_TEMPLATE = """**{location}:**
{items}"""

# Template for each listing item
ITEM_TEMPLATE = "• {material}{quantity} @ {price}"

# Variables that users can use in their templates
ALLOWED_VARS = [
    "company_code",
    "username",
    "date",
    "profile_url",
    "listings_by_location",  # Special: rendered listing groups
]

# Variables available per-listing (for advanced templates)
LISTING_VARS = [
    "material",
    "quantity",
    "price",
    "location",
    "notes",
]


def get_variable_help() -> str:
    """Return help text describing available template variables."""
    return """Available variables:
- {company_code} - Your company code (e.g., "ABC")
- {username} - Your FIO username
- {date} - Discord relative timestamp showing last sync
- {profile_url} - Link to your profile page
- {listings_by_location} - Auto-formatted listings grouped by location

The {listings_by_location} block formats as:
**Location Name:**
• MAT × 100 @ 1,500/u
• RAT × 50 @ CX.NC1-10%
"""


def format_price(listing) -> str:
    """Format a listing's price for Discord display."""
    from ..models import PriceType

    if listing.price_type == PriceType.ABSOLUTE:
        return f"{listing.price_value:,.0f}/u" if listing.price_value else "Contact me"
    elif listing.price_type == PriceType.CX_RELATIVE:
        if listing.price_value is None:
            return "CX price"
        sign = "+" if listing.price_value >= 0 else ""
        exchange = f".{listing.price_exchange}" if listing.price_exchange else ""
        if getattr(listing, 'price_cx_is_absolute', False):
            return f"CX{exchange}{sign}{listing.price_value:,.0f}"
        else:
            return f"CX{exchange}{sign}{listing.price_value:.0f}%"
    else:
        return "Contact me"


def render_listings_by_location(listings: list, include_emoji: bool = True) -> str:
    """
    Render listings grouped by location in the default format.

    Args:
        listings: List of Listing objects
        include_emoji: Whether to include bullet point emoji

    Returns:
        Formatted string with listings grouped by location
    """
    # Group listings by location
    by_location: dict[str, list] = {}
    for listing in listings:
        loc = listing.storage_name or listing.location or "Unknown"
        if loc not in by_location:
            by_location[loc] = []
        by_location[loc].append(listing)

    sections = []
    for location, loc_listings in by_location.items():
        items = []
        for listing in sorted(loc_listings, key=lambda l: l.material_ticker):
            price_str = format_price(listing)
            qty = listing.available_quantity if listing.available_quantity is not None else listing.quantity
            qty_str = f" × {qty:,}" if qty else ""
            prefix = "• " if include_emoji else "- "
            items.append(f"{prefix}{listing.material_ticker}{qty_str} @ {price_str}")

        section = f"**{location}:**\n" + "\n".join(items)
        sections.append(section)

    return "\n\n".join(sections)


def render_discord(user: "User", listings: list, base_url: str) -> str:
    """
    Render Discord-formatted text using the user's custom template or default.

    Args:
        user: User object with optional discord_template
        listings: List of Listing objects to include
        base_url: Base URL for profile links

    Returns:
        Formatted Discord message string
    """
    if not listings:
        return f"**[{user.company_code or '???'}] {user.fio_username}** has no active listings."

    template = user.discord_template or DEFAULT_TEMPLATE

    # Build context variables
    # Use Discord relative timestamp format based on last FIO sync
    sync_time = user.fio_last_synced or datetime.utcnow()
    unix_timestamp = int(sync_time.timestamp())
    date_str = f"<t:{unix_timestamp}:R>"

    profile_url = f"{base_url}/u/{user.fio_username}"

    # Build the listings_by_location content
    listings_by_location = render_listings_by_location(listings)

    # Prepare substitution context
    context = {
        "company_code": user.company_code or "???",
        "username": user.fio_username,
        "date": date_str,
        "profile_url": profile_url,
        "listings_by_location": listings_by_location,
    }

    # Perform substitution using safe string formatting
    result = template
    for var, value in context.items():
        result = result.replace("{" + var + "}", value)

    return result


def validate_template(template: str) -> tuple[bool, str | None]:
    """
    Validate a Discord template for common issues.

    Args:
        template: The template string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not template or not template.strip():
        return False, "Template cannot be empty"

    if len(template) > 2000:
        return False, "Template is too long (max 2000 characters)"

    # Check for unknown variables
    var_pattern = r'\{(\w+)\}'
    found_vars = re.findall(var_pattern, template)

    unknown_vars = [v for v in found_vars if v not in ALLOWED_VARS]
    if unknown_vars:
        return False, f"Unknown variable(s): {', '.join(unknown_vars)}"

    # Check that template includes listings_by_location for practical use
    if "{listings_by_location}" not in template:
        # Just a warning, not an error
        pass

    return True, None
