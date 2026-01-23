#!/usr/bin/env python3
"""Quick script to test FIO API responses."""

import asyncio
import httpx
import sys

FIO_API_BASE = "https://rest.fnar.net"


async def test_fio(username: str, api_key: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": api_key, "Accept": "application/json"}

        print(f"Testing FIO API for user: {username}")
        print("=" * 50)

        # Test 1: Get user planets
        print("\n1. GET /rain/userplanets/{username}")
        url = f"{FIO_API_BASE}/rain/userplanets/{username}"
        resp = await client.get(url, headers=headers)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Response: {data[:2] if len(data) > 2 else data}...")  # First 2 items
            print(f"   Total planets: {len(data)}")
        else:
            print(f"   Response: {resp.text[:200]}")

        # Test 2: Get user planet buildings
        print("\n2. GET /rain/userplanetbuildings/{username}")
        url = f"{FIO_API_BASE}/rain/userplanetbuildings/{username}"
        resp = await client.get(url, headers=headers)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Total buildings: {len(data)}")
            if data:
                first = data[0]
                print(f"   First building keys: {list(first.keys())}")
                print(f"   CompanyCode: {first.get('CompanyCode')}")
                print(f"   CompanyName: {first.get('CompanyName')}")
        else:
            print(f"   Response: {resp.text[:200]}")

        # Test 3: Get building recipes (public, no auth needed)
        print("\n3. GET /rain/buildingrecipes (public)")
        url = f"{FIO_API_BASE}/rain/buildingrecipes"
        resp = await client.get(url)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Total recipes: {len(data)}")

        # Test 4: Try the production endpoint
        print("\n4. GET /production/{username}")
        url = f"{FIO_API_BASE}/production/{username}"
        resp = await client.get(url, headers=headers)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Total production lines: {len(data)}")
        else:
            print(f"   Response: {resp.text[:200]}")

        # Test 5: Try sites endpoint
        print("\n5. GET /sites/{username}")
        url = f"{FIO_API_BASE}/sites/{username}"
        resp = await client.get(url, headers=headers)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Total sites: {len(data)}")
            if data:
                print(f"   First site keys: {list(data[0].keys())}")
        else:
            print(f"   Response: {resp.text[:200]}")

        # Test 6: Try company lookup by username
        print("\n6. GET /company/name/{username}")
        url = f"{FIO_API_BASE}/company/name/{username}"
        resp = await client.get(url)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Response: {data}")
        else:
            print(f"   Response: {resp.text[:200]}")

        # Test 7: Check sites data more closely
        print("\n7. Sites data (full first entry)")
        url = f"{FIO_API_BASE}/sites/{username}"
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                import json
                print(json.dumps(data[0], indent=2))

        # Test 8: Try storage endpoint
        print("\n8. GET /storage/{username}")
        url = f"{FIO_API_BASE}/storage/{username}"
        resp = await client.get(url, headers=headers)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Total storages: {len(data)}")
            if data:
                print(f"   First storage keys: {list(data[0].keys())}")
        else:
            print(f"   Response: {resp.text[:200]}")

        # Test 9: Extract building tickers from sites
        print("\n9. Building tickers from sites")
        url = f"{FIO_API_BASE}/sites/{username}"
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            sites = resp.json()
            tickers = set()
            for site in sites:
                for building in site.get("Buildings", []):
                    ticker = building.get("BuildingTicker")
                    if ticker:
                        tickers.add(ticker)
            print(f"   Unique building tickers: {sorted(tickers)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_fio.py <username> <api_key>")
        sys.exit(1)

    username = sys.argv[1]
    api_key = sys.argv[2]

    asyncio.run(test_fio(username, api_key))
