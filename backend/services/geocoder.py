"""
QuantaRoute — Nominatim Geocoder
Converts UK addresses/postcodes to lat/lng coordinates.
Free OpenStreetMap API — no key needed.
"""

import asyncio
import httpx
import logging
import re

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
POSTCODES_URL = "https://api.postcodes.io/postcodes"
HEADERS = {"User-Agent": "QuantaRoute/1.0"}
POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
    re.IGNORECASE,
)


def extract_uk_postcode(address: str) -> str | None:
    match = POSTCODE_RE.search(address)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1).upper())


async def geocode_postcode(client: httpx.AsyncClient, postcode: str) -> tuple | None:
    try:
        r = await client.get(
            f"{POSTCODES_URL}/{postcode}",
            headers=HEADERS,
            timeout=10.0,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        result = data.get("result")
        if not result:
            return None
        return (float(result["latitude"]), float(result["longitude"]))
    except Exception as e:
        logger.warning(f"Postcode lookup failed for {postcode}: {e}")
        return None


async def geocode_single(client: httpx.AsyncClient, address: str) -> tuple | None:
    try:
        postcode = extract_uk_postcode(address)
        if postcode:
            coord = await geocode_postcode(client, postcode)
            if coord:
                return coord

        r = await client.get(
            NOMINATIM_URL,
            params={
                "q": address + ", UK",
                "format": "json",
                "limit": 1,
                "countrycodes": "gb",
            },
            headers=HEADERS,
            timeout=10.0
        )
        r.raise_for_status()
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
