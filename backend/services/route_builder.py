"""
QuantaRoute — Route Builder
Chains geocoder + road matrix + QAOA into one complete pipeline.
Input: list of address strings
Output: optimised route with Google Maps URL + WhatsApp link
"""

import asyncio
import urllib.parse
import logging
import numpy as np

from geocoder import geocode_addresses
from road_matrix import build_distance_matrix
from qaoa import get_optimised_route, calculate_total_distance, estimate_fuel_saving

logger = logging.getLogger(__name__)


def build_google_maps_url(ordered_addresses: list[str]) -> str:
    if not ordered_addresses:
        return ""
    base = "https://www.google.com/maps/dir/"
    stops = "/".join(urllib.parse.quote(addr) for addr in ordered_addresses)
    return base + stops


def build_whatsapp_url(maps_url: str, driver_name: str = "Driver") -> str:
    """Build WhatsApp message URL with the route link."""
    message = (
        f"Hi {driver_name}! Your optimised route is ready. "
        f"Tap to open in Google Maps: {maps_url}"
    )
    encoded = urllib.parse.quote(message, safe=":/?=&,+%")
    return f"https://wa.me/?text={encoded}"

async def optimise_route(addresses: list[str], driver_name: str = "Driver") -> dict:
    """
    Full pipeline: addresses -> optimised route + URLs.
    """
    if len(addresses) < 2:
        raise ValueError("Need at least 2 addresses to optimise")

    print(f"\n[1/4] Geocoding {len(addresses)} addresses...")
    coords = await geocode_addresses(addresses)

    failed = [addresses[i] for i, c in enumerate(coords) if c is None]
    if failed:
        print(f"  Warning: Could not geocode: {failed}")

    valid_indices = [i for i, c in enumerate(coords) if c is not None]
    valid_coords = [coords[i] for i in valid_indices]
    valid_addresses = [addresses[i] for i in valid_indices]

    if len(valid_coords) < 2:
        failed_text = ", ".join(failed[:5]) if failed else "the provided stops"
        raise ValueError(
            f"Only {len(valid_coords)} stop(s) could be geocoded. "
            f"Use full UK postcodes or add the town/city. Failed: {failed_text}"
        )

    print(f"  Geocoded {len(valid_coords)}/{len(addresses)} addresses successfully")

    print(f"\n[2/4] Building road distance matrix...")
    matrix = build_distance_matrix(valid_coords)
    print(f"  Matrix built: {matrix.shape[0]}x{matrix.shape[1]}")

    print(f"\n[3/4] Running route optimisation...")
    naive_order = list(range(len(valid_coords)))
    naive_dist = calculate_total_distance(naive_order, matrix)

    optimised_order = get_optimised_route(matrix)
    optimised_dist = calculate_total_distance(optimised_order, matrix)
    fuel_saving = estimate_fuel_saving(naive_dist, optimised_dist)

    print(f"  Naive distance:     {naive_dist} km")
    print(f"  Optimised distance: {optimised_dist} km")
    print(f"  Fuel saving:        {fuel_saving}%")

    print(f"\n[4/4] Building delivery URLs...")
    ordered_coords = [valid_coords[i] for i in optimised_order]
    ordered_addresses = [valid_addresses[i] for i in optimised_order]

    maps_url = build_google_maps_url(ordered_addresses)   # ✅ FIXED — addresses not coords
    whatsapp_url = build_whatsapp_url(maps_url, driver_name)

    print(f"  Google Maps URL: {maps_url[:60]}...")
    print(f"  WhatsApp URL ready")

    return {
        "optimised_order": optimised_order,
        "ordered_addresses": ordered_addresses,
        "ordered_coords": ordered_coords,
        "total_distance_km": optimised_dist,
        "naive_distance_km": naive_dist,
        "fuel_saving_percent": fuel_saving,
        "maps_url": maps_url,
        "whatsapp_url": whatsapp_url,
        "stops_count": len(valid_coords),
        "geocoded_count": len(valid_coords),
        "failed_addresses": failed
    }


if __name__ == "__main__":
    print("=" * 55)
    print("  QuantaRoute Full Pipeline Test")
    print("=" * 55)

    test_addresses = [
        "PL1 2AB, Plymouth",
        "PL4 6AB, Plymouth",
        "PL2 1AA, Plymouth",
        "PL3 4BB, Plymouth",
    ]

    result = asyncio.run(optimise_route(test_addresses))

    print("\n" + "=" * 55)
    print("  RESULT")
    print("=" * 55)
    print(f"Stops:              {result['stops_count']}")
    print(f"Optimised order:    {result['optimised_order']}")
    print(f"Ordered addresses:  {result['ordered_addresses']}")
    print(f"Total distance:     {result['total_distance_km']} km")
    print(f"Fuel saving:        {result['fuel_saving_percent']}%")
    print(f"\nGoogle Maps URL:\n{result['maps_url']}")
    print(f"\nWhatsApp URL:\n{result['whatsapp_url']}")
    print("=" * 55)
