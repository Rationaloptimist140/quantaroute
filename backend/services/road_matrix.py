"""
QuantaRoute — OSRM Road Distance Matrix
Builds real road distance matrix using free OpenStreetMap routing.
No API key needed. Uses public OSRM server.
"""

import httpx
import numpy as np
import logging
import math

logger = logging.getLogger(__name__)

OSRM_URL = "http://router.project-osrm.org/table/v1/driving"


def is_valid_coordinate(coord: tuple | None) -> bool:
    if coord is None:
        return False
    try:
        if len(coord) != 2:
            return False
        lat = float(coord[0])
        lng = float(coord[1])
    except (TypeError, ValueError, IndexError):
        return False
    return math.isfinite(lat) and math.isfinite(lng)


def build_distance_matrix(coordinates: list[tuple]) -> np.ndarray:
    """
    Build NxN road distance matrix from list of (lat, lng) tuples.
    Uses OSRM /table endpoint for efficient batch calculation.
    Returns distances in km.
    """
    if not coordinates:
        return np.array([])

    # Filter out failed or malformed geocodes before OSRM receives them.
    valid_coords = [(i, c) for i, c in enumerate(coordinates) if is_valid_coordinate(c)]
    n = len(valid_coords)

    if n < 2:
        raise ValueError("Need at least 2 valid coordinates")

    # Format: lng,lat;lng,lat (OSRM uses lng first)
    coords_str = ";".join(f"{float(lng)},{float(lat)}" for _, (lat, lng) in valid_coords)
    url = f"{OSRM_URL}/{coords_str}"

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url, params={"annotations": "distance"})
            r.raise_for_status()
            data = r.json()

        if data.get("code") != "Ok":
            raise ValueError(f"OSRM error: {data.get('code')}")

        # Extract distance matrix (in metres) → convert to km
        durations = data.get("distances")
        if not durations or len(durations) != n or any(row is None or len(row) != n for row in durations):
            raise ValueError("OSRM returned an incomplete distance matrix")
        matrix = np.array(durations, dtype=float) / 1000.0
        if matrix.shape != (n, n) or not np.isfinite(matrix).all():
            raise ValueError("OSRM returned invalid distance values")

        # Set diagonal to 0 (distance from point to itself)
        np.fill_diagonal(matrix, 0.0)

        return matrix

    except Exception as e:
        logger.error(f"OSRM failed: {e}, falling back to Haversine")
        return haversine_matrix([c for _, c in valid_coords])


def haversine_distance(coord1: tuple, coord2: tuple) -> float:
    """Straight-line distance in km between two (lat, lng) points."""
    import math
    lat1, lon1 = map(math.radians, coord1)
    lat2, lon2 = map(math.radians, coord2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 6371 * 2 * math.asin(math.sqrt(a))


def haversine_matrix(coordinates: list[tuple]) -> np.ndarray:
    """Fallback: straight-line distance matrix when OSRM unavailable."""
    n = len(coordinates)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = haversine_distance(coordinates[i], coordinates[j])
    return matrix


if __name__ == "__main__":
    import asyncio
    from geocoder import geocode_addresses

    print("Testing road distance matrix...")
    print("Geocoding 3 UK cities...")

    addresses = ["PL1 2AB, Plymouth", "EX1 1AA, Exeter", "BS1 1AA, Bristol"]
    coords = asyncio.run(geocode_addresses(addresses))

    print(f"Coordinates: {coords}")

    valid = [c for c in coords if c is not None]
    print(f"\nBuilding road distance matrix for {len(valid)} locations...")

    matrix = build_distance_matrix(valid)

    print(f"\nRoad distance matrix (km):")
    print(matrix)
    print(f"\nPlymouth -> Exeter: {matrix[0][1]:.1f} km")
    print(f"Exeter -> Bristol:  {matrix[1][2]:.1f} km")
    print(f"Plymouth -> Bristol: {matrix[0][2]:.1f} km")
