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

    async def get_all_planets(self) -> list[dict]:
        """Get all planets in the game."""
        return await self._get("/planet/allplanets") or []

    async def get_building_recipes(self) -> list[dict]:
        """Get all building recipes (what each building can produce)."""
        return await self._get("/rain/buildingrecipes") or []

    async def get_recipe_outputs(self) -> list[dict]:
        """Get all recipe outputs (material outputs per recipe)."""
        return await self._get("/rain/recipeoutputs") or []

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

    async def get_user_info(self, username: str) -> Optional[dict]:
        """Get user info including company code/name."""
        return await self._get(f"/user/{username}")

    async def get_user_production(self, username: str) -> list[dict]:
        """Get user's production lines."""
        return await self._get(f"/production/{username}") or []

    async def get_user_storage(self, username: str) -> list[dict]:
        """Get user's storage (warehouses, base stores, ship stores, etc.)."""
        return await self._get(f"/storage/{username}") or []

    async def get_user_warehouses(self, username: str) -> list[dict]:
        """Get user's rented warehouse locations with names."""
        return await self._get(f"/sites/warehouses/{username}") or []

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
            # Try both possible field names
            ticker = building.get("BuildingTicker") or building.get("Ticker")
            if ticker:
                tickers.add(ticker)
    return tickers


def extract_active_production(production_lines: list[dict]) -> set[str]:
    """
    Extract material tickers that the user is actually producing.

    Production lines have Orders with Outputs containing MaterialTicker.
    """
    materials = set()
    for line in production_lines:
        for order in line.get("Orders", []):
            for output in order.get("Outputs", []):
                ticker = output.get("MaterialTicker")
                if ticker:
                    materials.add(ticker)
    return materials


def extract_storage_locations(
    storages: list[dict],
    sites: list[dict],
    warehouses: list[dict] = None,
    cx_station_names: set[str] = None,
) -> list[dict]:
    """
    Extract storage locations with human-readable names.

    Args:
        storages: Raw storage data from /storage/{username}
        sites: Site data from /sites/{username} - maps SiteId to planet
        warehouses: Warehouse data from /sites/warehouses/{username} - maps StoreId to location
        cx_station_names: Set of CX station names from database (e.g., {"Moria Station", ...})

    Returns list of dicts with:
    - addressable_id: The FIO storage identifier
    - type: STORE, WAREHOUSE_STORE, etc.
    - name: Human-readable name (planet name or CX/warehouse location)
    - is_cx: True if this is a CX station warehouse
    - items: Dict of material_ticker -> amount

    Results are sorted: CX stations first (alphabetically), then planets (alphabetically)
    """
    warehouses = warehouses or []
    cx_station_names = cx_station_names or set()

    # Build a map of SiteId -> PlanetName from sites (for base STORE types)
    site_to_planet = {}
    for site in sites:
        site_id = site.get("SiteId")
        planet_name = site.get("PlanetName") or site.get("PlanetIdentifier")
        if site_id and planet_name:
            site_to_planet[site_id] = planet_name

    # Build a map of StorageId -> LocationName from warehouses (for WAREHOUSE_STORE types)
    storage_to_location = {}
    for wh in warehouses:
        store_id = wh.get("StoreId")
        location_name = wh.get("LocationName") or wh.get("LocationNaturalId")
        if store_id and location_name:
            storage_to_location[store_id] = location_name

    result = []
    for storage in storages:
        addressable_id = storage.get("AddressableId", "")
        storage_id = storage.get("StorageId", "")
        storage_type = storage.get("Type", "")
        storage_name = storage.get("Name")  # Some storages have explicit names

        # Try to find a human-readable name
        name = None

        # 1. Check if storage has an explicit name
        if storage_name:
            name = storage_name

        # 2. For WAREHOUSE_STORE, look up by StorageId in warehouses
        elif storage_type == "WAREHOUSE_STORE" and storage_id in storage_to_location:
            name = storage_to_location[storage_id]

        # 3. For STORE, look up by AddressableId (which equals SiteId for base stores)
        elif storage_type == "STORE" and addressable_id in site_to_planet:
            name = site_to_planet[addressable_id]

        # 4. Fallback to truncated ID
        if not name:
            name = addressable_id[:12] if addressable_id else "Unknown"

        # Check if this is a CX station
        is_cx = name in cx_station_names

        # Extract items
        items = {}
        for item in storage.get("StorageItems", []):
            ticker = item.get("MaterialTicker")
            amount = item.get("MaterialAmount", 0)
            if ticker:
                items[ticker] = items.get(ticker, 0) + amount

        result.append({
            "addressable_id": addressable_id,
            "type": storage_type,
            "name": name,
            "is_cx": is_cx,
            "items": items,
        })

    # Sort: CX stations first, then by name, then base stores before warehouses
    # Sort key: (is_cx descending, name, type where STORE comes before WAREHOUSE_STORE)
    result.sort(key=lambda s: (
        0 if s["is_cx"] else 1,
        s["name"].lower(),
        0 if s["type"] == "STORE" else 1
    ))

    return result


def get_material_inventory(
    storages: list[dict], material_ticker: str
) -> list[dict]:
    """
    Get all storages containing a specific material.

    Returns list of dicts with:
    - addressable_id, type, name (from storage)
    - amount: quantity of the material in that storage
    """
    result = []
    for storage in storages:
        items = storage.get("items", {})
        if material_ticker in items:
            result.append({
                "addressable_id": storage["addressable_id"],
                "type": storage["type"],
                "name": storage["name"],
                "amount": items[material_ticker],
            })
    return result


def build_production_map(sites: list[dict], recipe_outputs: list[dict]) -> dict[str, list[str]]:
    """
    Given a user's sites and the recipe output data, determine what they CAN produce.
    Returns a dict mapping material tickers to list of building tickers that can make them.

    Recipe outputs have format: {'Key': 'SME-AL', 'Material': 'AL', 'Amount': 3}
    where the Key is "{BuildingTicker}-{RecipeName}"
    """
    # Get unique building tickers from all sites
    user_building_tickers = extract_building_tickers_from_sites(sites)

    # Map recipe outputs to materials
    # Key format is "BUILDING-RECIPE", e.g., "SME-AL" means Smelter produces AL
    production_map = {}
    for output in recipe_outputs:
        key = output.get("Key", "")
        material = output.get("Material")

        if not key or not material:
            continue

        # Extract building ticker from key (everything before first hyphen)
        parts = key.split("-")
        if len(parts) < 2:
            continue

        building_ticker = parts[0]

        if building_ticker not in user_building_tickers:
            continue

        if material not in production_map:
            production_map[material] = []
        if building_ticker not in production_map[material]:
            production_map[material].append(building_ticker)

    return production_map
