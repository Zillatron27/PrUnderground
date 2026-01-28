"""Admin access control and utilities."""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import User

# Admin usernames from environment variable
# Format: comma-separated list of FIO usernames
# Example: ADMIN_USERNAMES=Zillatron,OtherAdmin
_admin_usernames_raw = os.getenv("ADMIN_USERNAMES", "")
ADMIN_USERNAMES = [
    name.strip()
    for name in _admin_usernames_raw.split(",")
    if name.strip()
]


def is_admin(user: "User | None") -> bool:
    """
    Check if a user has admin privileges.

    Args:
        user: The user to check, or None

    Returns:
        True if user is an admin, False otherwise
    """
    if not user:
        return False
    return user.fio_username in ADMIN_USERNAMES
