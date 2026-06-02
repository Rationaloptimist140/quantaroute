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
PHOTON_URL = "https://photon.komoot.io/api/"
POSTCODES_URL = "https://api.postcodes.io/postcodes"
TERMINATED_POSTCODES_URL = "https://api.postcodes.io/terminated_postcodes"
OUTCODES_URL = "https://api.postcodes.io/outcodes"
HEADERS = {"User-Agent": "QuantaRoute/1.0 (hi@quantaroute.co.uk)"}
POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
    re.IGNORECASE,
)
OUTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\b", re.IGNORECASE)


def extract_uk_postcode(address: str) -> str | None:
    match = POSTCODE_RE.search(address)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1).upper())


def extract_uk_outcode(address: str) -> str | None:
    match = OUTCODE_RE.search(address)
    if not match:
        return None
    return match.group(1).upper()


def outcode_from_postcode(postcode: str) -> str:
    return postcode[:-3].upper()


async def lookup_postcode_endpoint(
    client: httpx.AsyncClient,
    base_url: str,
    postcode: str,
) -> tuple | None:
    try:
        r = await client.get(
            f"{base_url}/{postcode}",
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
        logger.warning(f"Postcode lookup failed for {postcode} at {base_url}: {e}")
        return None


async def geocode_postcode(client: httpx.AsyncClient, postcode: str) -> tuple | None:
    return (
        await lookup_postcode_endpoint(client, POSTCODES_URL, postcode)
        or await lookup_postcode_endpoint(client, TERMINATED_POSTCODES_URL, postcode)
    )


async def geocode_outcode(client: httpx.AsyncClient, outcode: str) -> tuple | None:
    try:
        r = await client.get(
            f"{OUTCODES_URL}/{outcode}",
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
        logger.warning(f"Outcode lookup failed for {outcode}: {e}")
        return None


async def geocode_photon(client: httpx.AsyncClient, address: str) -> tuple | None:
    try:
        r = await client.get(
            PHOTON_URL,
            params={
                "q": f"{address}, UK",
                "limit": 1,
                "lang": "en",
            },
            headers=HEADERS,
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        features = data.get("features") or []
        if not features:
            return None
        properties = features[0].get("properties") or {}
        if properties.get("countrycode") not in {None, "GB", "gb"}:
            return None
        coordinates = features[0].get("geometry", {}).get("coordinates")
        if not coordinates or len(coordinates) < 2:
            return None
        lng, lat = coordinates[:2]
        return (float(lat), float(lng))
    except Exception as e:
        logger.warning(f"Photon lookup failed for {address}: {e}")
        return None


async def geocode_single_with_source(
    client: httpx.AsyncClient,
    address: str,
) -> tuple[tuple | None, bool]:
    used_nominatim = False
    try:
        postcode = extract_uk_postcode(address)
        if postcode:
            coord = await geocode_postcode(client, postcode)
            if coord:
                return coord, used_nominatim

        outcode = outcode_from_postcode(postcode) if postcode else extract_uk_outcode(address)
        if outcode:
            coord = await geocode_outcode(client, outcode)
            if coord:
                return coord, used_nominatim

        used_nominatim = True
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
            return (float(data[0]["lat"]), float(data[0]["lon"])), used_nominatim
        coord = await geocode_photon(client, address)
        if coord:
            return coord, used_nominatim
        logger.warning(f"No result for: {address}")
        return None, used_nominatim
    except Exception as e:
        logger.error(f"Geocode failed for {address}: {e}")
        return None, used_nominatim


async def geocode_single(client: httpx.AsyncClient, address: str) -> tuple | None:
    coord, _used_nominatim = await geocode_single_with_source(client, address)
    return coord


async def geocode_addresses(addresses: list[str]) -> list[tuple | None]:
    """
    Convert list of UK addresses/postcodes to (lat, lng) tuples.
    Respects Nominatim 1 request/second rate limit.
    """
    results = []
    async with httpx.AsyncClient() as client:
        for i, address in enumerate(addresses):
            coord, used_nominatim = await geocode_single_with_source(client, address)
            results.append(coord)
            logger.info(f"Geocoded {i+1}/{len(addresses)}: {address} -> {coord}")
            if used_nominatim and i < len(addresses) - 1:
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
