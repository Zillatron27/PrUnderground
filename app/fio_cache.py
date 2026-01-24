"""
FIO API Cache Layer

Caches FIO API responses per-user with a configurable TTL.
Provides manual refresh capability.
"""

from datetime import datetime, timedelta
from typing import Optional, Any
from dataclasses import dataclass, field

# Default cache TTL: 10 minutes
DEFAULT_TTL_SECONDS = 600


@dataclass
class CacheEntry:
    """A single cache entry with data and expiration."""
    data: Any
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at


@dataclass
class UserFIOCache:
    """Cached FIO data for a single user."""
    production: Optional[CacheEntry] = None
    storage: Optional[CacheEntry] = None
    sites: Optional[CacheEntry] = None
    warehouses: Optional[CacheEntry] = None
    # Computed/derived data
    suggestions: Optional[CacheEntry] = None
    storage_locations: Optional[CacheEntry] = None
    last_refresh: Optional[datetime] = None


class FIOCache:
    """
    In-memory cache for FIO API data.

    Stores data per-user with TTL expiration.
    Also caches global (public) data like all_materials.
    Thread-safe for single-process async usage.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, UserFIOCache] = {}
        # Global cache for public data (not user-specific)
        self._all_materials: Optional[CacheEntry] = None

    def _get_user_cache(self, username: str) -> UserFIOCache:
        """Get or create cache for a user."""
        username = username.lower()
        if username not in self._cache:
            self._cache[username] = UserFIOCache()
        return self._cache[username]

    def _make_entry(self, data: Any) -> CacheEntry:
        """Create a cache entry with TTL."""
        return CacheEntry(
            data=data,
            expires_at=datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
        )

    def get_production(self, username: str) -> Optional[list]:
        """Get cached production data if valid."""
        cache = self._get_user_cache(username)
        if cache.production and not cache.production.is_expired():
            return cache.production.data
        return None

    def set_production(self, username: str, data: list):
        """Cache production data."""
        cache = self._get_user_cache(username)
        cache.production = self._make_entry(data)

    def get_storage(self, username: str) -> Optional[list]:
        """Get cached storage data if valid."""
        cache = self._get_user_cache(username)
        if cache.storage and not cache.storage.is_expired():
            return cache.storage.data
        return None

    def set_storage(self, username: str, data: list):
        """Cache storage data."""
        cache = self._get_user_cache(username)
        cache.storage = self._make_entry(data)

    def get_sites(self, username: str) -> Optional[list]:
        """Get cached sites data if valid."""
        cache = self._get_user_cache(username)
        if cache.sites and not cache.sites.is_expired():
            return cache.sites.data
        return None

    def set_sites(self, username: str, data: list):
        """Cache sites data."""
        cache = self._get_user_cache(username)
        cache.sites = self._make_entry(data)

    def get_warehouses(self, username: str) -> Optional[list]:
        """Get cached warehouses data if valid."""
        cache = self._get_user_cache(username)
        if cache.warehouses and not cache.warehouses.is_expired():
            return cache.warehouses.data
        return None

    def set_warehouses(self, username: str, data: list):
        """Cache warehouses data."""
        cache = self._get_user_cache(username)
        cache.warehouses = self._make_entry(data)

    def get_suggestions(self, username: str) -> Optional[list]:
        """Get cached suggestions if valid."""
        cache = self._get_user_cache(username)
        if cache.suggestions and not cache.suggestions.is_expired():
            return cache.suggestions.data
        return None

    def set_suggestions(self, username: str, data: list):
        """Cache suggestions."""
        cache = self._get_user_cache(username)
        cache.suggestions = self._make_entry(data)

    def get_storage_locations(self, username: str) -> Optional[list]:
        """Get cached storage locations if valid."""
        cache = self._get_user_cache(username)
        if cache.storage_locations and not cache.storage_locations.is_expired():
            return cache.storage_locations.data
        return None

    def set_storage_locations(self, username: str, data: list):
        """Cache storage locations."""
        cache = self._get_user_cache(username)
        cache.storage_locations = self._make_entry(data)

    # Global (public) data methods
    def get_all_materials(self) -> Optional[list]:
        """Get cached all_materials if valid."""
        if self._all_materials and not self._all_materials.is_expired():
            return self._all_materials.data
        return None

    def set_all_materials(self, data: list):
        """Cache all_materials (global, not per-user)."""
        self._all_materials = self._make_entry(data)

    def get_last_refresh(self, username: str) -> Optional[datetime]:
        """Get the timestamp of last FIO refresh for a user."""
        cache = self._get_user_cache(username)
        return cache.last_refresh

    def set_last_refresh(self, username: str):
        """Update the last refresh timestamp."""
        cache = self._get_user_cache(username)
        cache.last_refresh = datetime.utcnow()

    def invalidate_user(self, username: str):
        """Clear all cached data for a user (force refresh)."""
        username = username.lower()
        if username in self._cache:
            del self._cache[username]

    def get_cache_status(self, username: str) -> dict:
        """Get cache status for display (what's cached, when it expires)."""
        cache = self._get_user_cache(username)
        now = datetime.utcnow()

        def entry_status(entry: Optional[CacheEntry]) -> dict:
            if not entry:
                return {"cached": False}
            if entry.is_expired():
                return {"cached": False, "expired": True}
            seconds_left = (entry.expires_at - now).total_seconds()
            return {"cached": True, "expires_in_seconds": int(seconds_left)}

        return {
            "production": entry_status(cache.production),
            "storage": entry_status(cache.storage),
            "sites": entry_status(cache.sites),
            "warehouses": entry_status(cache.warehouses),
            "suggestions": entry_status(cache.suggestions),
            "storage_locations": entry_status(cache.storage_locations),
            "last_refresh": cache.last_refresh.isoformat() if cache.last_refresh else None,
        }


# Global cache instance
fio_cache = FIOCache()
