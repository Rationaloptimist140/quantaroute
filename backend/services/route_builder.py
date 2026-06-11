"""
QuantaRoute — Route Builder
Chains geocoder + road matrix + route selection into one complete pipeline.
Input: list of address strings
Output: optimised route with Google Maps URL + WhatsApp link
"""

import asyncio
import urllib.parse
import logging
import re
import numpy as np

from geocoder import geocode_addresses
from road_matrix import build_distance_matrix, is_valid_coordinate
from qaoa import estimate_fuel_saving, nearest_neighbour_route

logger = logging.getLogger(__name__)

GEOCODING_HELP_MESSAGE = "Could not find this address. Try adding postcode, city, or full business address."


class RouteGeocodingError(ValueError):
    def __init__(self, failed_addresses: list[str]):
        self.failed_addresses = failed_addresses
        failed_text = ", ".join(failed_addresses)
        super().__init__(f"{GEOCODING_HELP_MESSAGE} Failed: {failed_text}")

    def as_details(self) -> list[dict[str, str]]:
        return [
            {
                "address": address,
                "message": GEOCODING_HELP_MESSAGE,
            }
            for address in self.failed_addresses
        ]


def clean_route_address(address: str) -> str:
    text = str(address or "").strip()
    text = re.sub(r"^\ufeff", "", text).strip()
    text = re.sub(r"^\d+\s*,\s*", "", text).strip()
    text = text.strip(",").strip()
    text = re.sub(r"^[\"']+", "", text).strip()
    text = re.sub(r"[\"']+$", "", text).strip()
    return text.strip(",").strip()


def build_google_maps_url(
    ordered_addresses: list[str],
    start_address: str | None = None,
    return_to_start: bool = False,
    end_address: str | None = None,
) -> str:
    clean_start = clean_route_address(start_address or "")
    clean_end = clean_route_address(end_address or "")
    clean_addresses = [clean_route_address(addr) for addr in ordered_addresses]
    clean_addresses = [addr for addr in clean_addresses if addr]
    route_addresses = ([clean_start] if clean_start else []) + clean_addresses
    if clean_end:
        route_addresses.append(clean_end)
    elif clean_start and return_to_start:
        route_addresses.append(clean_start)
    if not route_addresses:
        return ""
    base = "https://www.google.com/maps/dir/"
    stops = "/".join(urllib.parse.quote(addr) for addr in route_addresses)
    return base + stops


def build_whatsapp_message(maps_url: str, driver_name: str = "Driver") -> str:
    return (
        f"Hi {driver_name}! Your optimised route is ready. "
        f"Tap to open in Google Maps: {maps_url}"
    )


def build_whatsapp_url(maps_url: str, driver_name: str = "Driver") -> str:
    """Build WhatsApp message URL with the route link."""
    message = build_whatsapp_message(maps_url, driver_name)
    encoded = urllib.parse.quote(message, safe=":/?=&,+%")
    return f"https://wa.me/?text={encoded}"


def describe_route_algorithm(stops_count: int) -> str:
    if stops_count < 8:
        return "exact brute force"
    return "nearest-neighbour heuristic"


def select_route_order(
    matrix: np.ndarray,
    requested_stops_count: int,
) -> tuple[list[int], str]:
    if len(matrix) < 8:
        from qaoa import brute_force_route

        return brute_force_route(matrix), "exact brute force"
    return nearest_neighbour_route(matrix), "nearest-neighbour heuristic"


def calculate_path_distance(order: list[int], matrix: np.ndarray) -> float:
    total = 0.0
    for i in range(len(order) - 1):
        total += matrix[order[i]][order[i + 1]]
    return round(total, 2)


async def optimise_route(
    addresses: list[str],
    driver_name: str = "Driver",
    start_address: str | None = None,
    return_to_start: bool = False,
    end_address: str | None = None,
) -> dict:
    """
    Full pipeline: addresses -> optimised route + URLs.
    """
    addresses = [clean_route_address(address) for address in addresses]
    addresses = [address for address in addresses if address]
    clean_start_address = clean_route_address(start_address or "")
    clean_end_address = clean_route_address(end_address or "")

    if len(addresses) < 2:
        raise ValueError("Need at least 2 addresses to optimise")

    print(f"\n[1/4] Geocoding {len(addresses)} addresses...")
    coords = await geocode_addresses(addresses)

    failed = [addresses[i] for i, c in enumerate(coords) if not is_valid_coordinate(c)]
    if failed:
        print(f"  Warning: Could not geocode: {failed}")
        raise RouteGeocodingError(failed)

    valid_indices = [i for i, c in enumerate(coords) if is_valid_coordinate(c)]
    valid_coords = [coords[i] for i in valid_indices]
    valid_addresses = [addresses[i] for i in valid_indices]

    boundary_addresses = [
        address for address in [clean_start_address, clean_end_address] if address
    ]
    boundary_coords = []
    if boundary_addresses:
        boundary_coords = await geocode_addresses(boundary_addresses)
        failed_boundaries = [
            boundary_addresses[i]
            for i, coord in enumerate(boundary_coords)
            if not is_valid_coordinate(coord)
        ]
        if failed_boundaries:
            print(f"  Warning: Could not geocode route boundary: {failed_boundaries}")
            raise RouteGeocodingError(failed_boundaries)

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
    original_order = list(range(len(valid_coords)))
    nn_order = nearest_neighbour_route(matrix)
    algorithm_name = describe_route_algorithm(len(valid_coords))

    optimised_order, algorithm_used = select_route_order(matrix, len(addresses))

    start_coord = boundary_coords[0] if clean_start_address else None
    end_coord = None
    if clean_end_address:
        end_coord = boundary_coords[-1]

    combined_coords = []
    start_index = None
    if start_coord:
        start_index = len(combined_coords)
        combined_coords.append(start_coord)

    delivery_offset = len(combined_coords)
    combined_coords.extend(valid_coords)

    end_index = None
    if end_coord:
        end_index = len(combined_coords)
        combined_coords.append(end_coord)
    elif start_index is not None and return_to_start:
        end_index = start_index

    combined_matrix = build_distance_matrix(combined_coords)

    def delivery_path(order: list[int]) -> list[int]:
        path = []
        if start_index is not None:
            path.append(start_index)
        path.extend(delivery_offset + index for index in order)
        if end_index is not None:
            path.append(end_index)
        return path

    original_order_distance = calculate_path_distance(
        delivery_path(original_order),
        combined_matrix,
    )
    nearest_neighbour_distance = calculate_path_distance(
        delivery_path(nn_order),
        combined_matrix,
    )
    optimised_dist = calculate_path_distance(
        delivery_path(optimised_order),
        combined_matrix,
    )
    optimiser_vs_original = estimate_fuel_saving(original_order_distance, optimised_dist)
    optimiser_vs_nn = estimate_fuel_saving(nearest_neighbour_distance, optimised_dist)

    print(f"  Algorithm selected: {algorithm_name}")
    print(f"  Algorithm used:     {algorithm_used}")
    print(f"  Input order distance:       {original_order_distance} km")
    print(f"  Nearest-neighbour distance: {nearest_neighbour_distance} km")
    print(f"  Final selected distance:    {optimised_dist} km")
    print(f"  Optimiser vs input order:   {optimiser_vs_original}%")
    print(f"  Optimiser vs nearest-neighbour: {optimiser_vs_nn}%")

    if optimised_dist > original_order_distance:
        logger.warning(
            "Optimised route was longer than naive order (%s km > %s km); using naive order",
            optimised_dist,
            original_order_distance,
        )
        algorithm_used = f"input order safety fallback after {algorithm_used}"
        optimised_order = original_order
        optimised_dist = original_order_distance
        fuel_saving = 0.0
    else:
        fuel_saving = estimate_fuel_saving(original_order_distance, optimised_dist)

    final_selected_distance = optimised_dist
    fuel_saving_vs_original = fuel_saving

    print(f"  Returned route distance:    {optimised_dist} km")
    print(f"  Returned fuel saving:       {fuel_saving}%")

    print(f"\n[4/4] Building delivery URLs...")
    ordered_coords = [valid_coords[i] for i in optimised_order]
    ordered_addresses = [valid_addresses[i] for i in optimised_order]

    maps_url = build_google_maps_url(
        ordered_addresses,
        start_address=clean_start_address,
        return_to_start=return_to_start,
        end_address=clean_end_address,
    )
    whatsapp_url = build_whatsapp_url(maps_url, driver_name)

    print(f"  Google Maps URL: {maps_url[:60]}...")
    print(f"  WhatsApp URL ready")

    return {
        "optimised_order": optimised_order,
        "ordered_addresses": ordered_addresses,
        "start_address": clean_start_address or None,
        "return_to_start": bool(clean_start_address and return_to_start and not clean_end_address),
        "end_address": clean_end_address or None,
        "ordered_coords": ordered_coords,
        "total_distance_km": optimised_dist,
        "naive_distance_km": original_order_distance,
        "fuel_saving_percent": fuel_saving,
        "original_order_distance_km": original_order_distance,
        "nearest_neighbour_distance_km": nearest_neighbour_distance,
        "final_selected_distance_km": final_selected_distance,
        "fuel_saving_percent_vs_original": fuel_saving_vs_original,
        "algorithm_used": algorithm_used,
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
