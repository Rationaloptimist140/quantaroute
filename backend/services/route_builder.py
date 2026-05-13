"""
QuantaRoute — Route Builder
Chains geocoder + road matrix + QAOA into one complete pipeline.
Input: list of address strings
Output: optimised route with Google Maps URL + WhatsApp link
"""

import asyncio
import urllib.parse
import logging
import re
import numpy as np

from geocoder import geocode_addresses
from road_matrix import build_distance_matrix
from qaoa import (
    calculate_total_distance,
    estimate_fuel_saving,
    get_optimised_route_with_algorithm,
    nearest_neighbour_route,
)

logger = logging.getLogger(__name__)


def clean_route_address(address: str) -> str:
    text = str(address or "").strip()
    text = re.sub(r"^\ufeff", "", text).strip()
    text = re.sub(r"^\d+\s*,\s*", "", text).strip()
    text = text.strip(",").strip()
    text = re.sub(r"^[\"']+", "", text).strip()
    text = re.sub(r"[\"']+$", "", text).strip()
    return text.strip(",").strip()


def build_google_maps_url(ordered_addresses: list[str]) -> str:
    clean_addresses = [clean_route_address(addr) for addr in ordered_addresses]
    clean_addresses = [addr for addr in clean_addresses if addr]
    if not clean_addresses:
        return ""
    base = "https://www.google.com/maps/dir/"
    stops = "/".join(urllib.parse.quote(addr) for addr in clean_addresses)
    return base + stops


def build_whatsapp_url(maps_url: str, driver_name: str = "Driver") -> str:
    """Build WhatsApp message URL with the route link."""
    message = (
        f"Hi {driver_name}! Your optimised route is ready. "
        f"Tap to open in Google Maps: {maps_url}"
    )
    encoded = urllib.parse.quote(message, safe=":/?=&,+%")
    return f"https://wa.me/?text={encoded}"


def describe_route_algorithm(stops_count: int) -> str:
    if stops_count < 8:
        return "exact brute force"
    if stops_count <= 20:
        return "Qiskit QAOA quantum simulation"
    return "nearest-neighbour heuristic"

async def optimise_route(addresses: list[str], driver_name: str = "Driver") -> dict:
    """
    Full pipeline: addresses -> optimised route + URLs.
    """
    addresses = [clean_route_address(address) for address in addresses]
    addresses = [address for address in addresses if address]

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
    nn_order = nearest_neighbour_route(matrix)
    nn_dist = calculate_total_distance(nn_order, matrix)
    algorithm_name = describe_route_algorithm(len(valid_coords))

    optimised_order, algorithm_used = get_optimised_route_with_algorithm(matrix)
    optimised_dist = calculate_total_distance(optimised_order, matrix)
    optimiser_dist = optimised_dist
    optimiser_vs_naive = estimate_fuel_saving(naive_dist, optimiser_dist)
    optimiser_vs_nn = estimate_fuel_saving(nn_dist, optimiser_dist)

    print(f"  Algorithm selected: {algorithm_name}")
    print(f"  Algorithm used:     {algorithm_used}")
    print(f"  Input order distance:       {naive_dist} km")
    print(f"  Nearest-neighbour distance: {nn_dist} km")
    print(f"  Optimised/QAOA distance:    {optimiser_dist} km")
    print(f"  Optimiser vs input order:   {optimiser_vs_naive}%")
    print(f"  Optimiser vs nearest-neighbour: {optimiser_vs_nn}%")

    if optimised_dist > naive_dist:
        logger.warning(
            "Optimised route was longer than naive order (%s km > %s km); using naive order",
            optimised_dist,
            naive_dist,
        )
        optimised_order = naive_order
        optimised_dist = naive_dist
        fuel_saving = 0.0
    else:
        fuel_saving = estimate_fuel_saving(naive_dist, optimised_dist)

    print(f"  Returned route distance:    {optimised_dist} km")
    print(f"  Returned fuel saving:       {fuel_saving}%")

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
