import os
from typing import Optional
import httpx

FIO_API_BASE = os.getenv("FIO_API_BASE", "https://rest.fnar.net")


class FIOClient:
    """Client for interacting with the FIO API."""

    def __init__(self, api_key: Optional[str] = None):
        self.base_url = FIO_API_BASE
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._client.aclose()

    def _get_headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    async def _get(self, endpoint: str) -> Optional[dict | list]:
        """Make a GET request to the FIO API."""
        url = f"{self.base_url}{endpoint}"
        response = await self._client.get(url, headers=self._get_headers())

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 204:
            return None  # No content / not found
        elif response.status_code == 401:
            raise FIOAuthError("Authentication failed - check API key")
        else:
            raise FIOError(f"FIO API error: {response.status_code}")

    # --- Public Endpoints (no auth required) ---

    async def get_all_materials(self) -> list[dict]:
        """Get all materials in the game."""
        return await self._get("/material/allmaterials") or []

    async def get_material(self, ticker: str) -> Optional[dict]:
        """Get a specific material by ticker."""
        return await self._get(f"/material/{ticker}")

    async def get_all_buildings(self) -> list[dict]:
        """Get all building types."""
        return await self._get("/building/allbuildings") or []

    async def get_building_recipes(self) -> list[dict]:
        """Get all building recipes (what each building can produce)."""
        return await self._get("/rain/buildingrecipes") or []

    async def get_exchange_all(self) -> list[dict]:
        """Get all exchange data with current prices."""
        return await self._get("/exchange/all") or []

    async def get_exchange(self, ticker: str) -> Optional[dict]:
        """Get specific exchange data (e.g., 'RAT.NC1')."""
        return await self._get(f"/exchange/{ticker}")

    async def get_company_by_code(self, code: str) -> Optional[dict]:
        """Get company info by company code."""
        return await self._get(f"/company/code/{code}")

    # --- Authenticated Endpoints ---

    async def get_user_planet_buildings(self, username: str) -> list[dict]:
        """Get buildings constructed by a user (requires auth or permission)."""
        return await self._get(f"/rain/userplanetbuildings/{username}") or []

    async def get_user_sites(self, username: str) -> list[dict]:
        """Get user's sites with full building details."""
        return await self._get(f"/sites/{username}") or []

    async def get_user_planets(self, username: str) -> list[dict]:
        """Get planets owned by a user."""
        return await self._get(f"/rain/userplanets/{username}") or []

    async def get_user_production(self, username: str) -> list[dict]:
        """Get user's production lines."""
        return await self._get(f"/production/{username}") or []

    async def verify_api_key(self, username: str) -> dict:
        """
        Verify an API key by attempting to fetch user data.
        Returns user data if successful, raises FIOAuthError if not.
        """
        # Try to get user's sites - this requires valid auth and has the most data
        sites = await self.get_user_sites(username)
        if sites is None:
            raise FIOAuthError("Could not verify API key - no data returned")

        # Get planets for location info
        planets = await self.get_user_planets(username)

        return {
            "username": username,
            "sites": sites,
            "planets": planets or [],
        }


class FIOError(Exception):
    """Base exception for FIO API errors."""

    pass


class FIOAuthError(FIOError):
    """Authentication error with FIO API."""

    pass


# --- Helper functions ---


def extract_building_tickers_from_sites(sites: list[dict]) -> set[str]:
    """Extract unique building tickers from sites data."""
    tickers = set()
    for site in sites:
        for building in site.get("Buildings", []):
            ticker = building.get("BuildingTicker")
            if ticker:
                tickers.add(ticker)
    return tickers


def build_production_map(sites: list[dict], recipes: list[dict]) -> dict[str, list[str]]:
    """
    Given a user's sites and the recipe data, determine what they can produce.
    Returns a dict mapping material tickers to list of building tickers that can make them.
    """
    # Get unique building tickers from all sites
    user_building_tickers = extract_building_tickers_from_sites(sites)

    # Map recipes to outputs
    production_map = {}
    for recipe in recipes:
        building_ticker = recipe.get("BuildingTicker")
        if building_ticker not in user_building_tickers:
            continue

        outputs = recipe.get("Outputs", [])
        for output in outputs:
            material = output.get("MaterialTicker") or output.get("Ticker")
            if material:
                if material not in production_map:
                    production_map[material] = []
                if building_ticker not in production_map[material]:
                    production_map[material].append(building_ticker)

    return production_map
