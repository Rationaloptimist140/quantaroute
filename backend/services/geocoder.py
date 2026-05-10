"""
QuantaRoute — Nominatim Geocoder
Converts UK addresses/postcodes to lat/lng coordinates.
Free OpenStreetMap API — no key needed.
"""

import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "QuantaRoute/1.0"}


async def geocode_single(client: httpx.AsyncClient, address: str) -> tuple | None:
    try:
        r = await client.get(
            NOMINATIM_URL,
            params={"q": address + ", UK", "format": "json", "limit": 1},
            headers=HEADERS,
            timeout=10.0
        )
        data = r.json()
        if data:
            return (float(data[0]["lat"]), float(data[0]["lon"]))
        logger.warning(f"No result for: {address}")
        return None
    except Exception as e:
        logger.error(f"Geocode failed for {address}: {e}")
        return None


async def geocode_addresses(addresses: list[str]) -> list[tuple | None]:
    """
    Convert list of UK addresses/postcodes to (lat, lng) tuples.
    Respects Nominatim 1 request/second rate limit.
    """
    results = []
    async with httpx.AsyncClient() as client:
        for i, address in enumerate(addresses):
            coord = await geocode_single(client, address)
            results.append(coord)
            logger.info(f"Geocoded {i+1}/{len(addresses)}: {address} -> {coord}")
            if i < len(addresses) - 1:
                await asyncio.sleep(1)  # Nominatim rate limit
    return results


if __name__ == "__main__":
    test_addresses = [
        "Plymouth City Centre, PL1",
        "Exeter City Centre, EX1",
        "Bristol City Centre, BS1",
    ]

    print("Testing Nominatim geocoder...")
    results = asyncio.run(geocode_addresses(test_addresses))

    for addr, coord in zip(test_addresses, results):
        print(f"  {addr} -> {coord}")

    print(f"\nGeocoded {sum(1 for r in results if r)} / {len(results)} addresses successfully")