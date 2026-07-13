"""Export an offline route problem JSON for solver experiments.

This script is for research and benchmarking only. It does not call external
quantum, QUBO, hybrid, geocoding, or routing APIs.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
SERVICES_DIR = BACKEND_DIR / "services"
for path in (BACKEND_DIR, SERVICES_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from database import get_route_by_id, using_postgres  # noqa: E402
from qaoa import brute_force_route, estimate_fuel_saving, nearest_neighbour_route  # noqa: E402
from route_builder import calculate_path_distance  # noqa: E402


PRODUCTION_BASELINE_NOTE = (
    "Offline research/benchmarking only. Production routing does not depend on "
    "external quantum solvers. Current production baseline uses exact brute force "
    "below 8 geocoded stops and nearest-neighbour heuristic for 8+ geocoded stops."
)


DEMO_STOPS = [
    {
        "index": 0,
        "address": "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
        "lat": 50.3778,
        "lng": -4.1437,
    },
    {
        "index": 1,
        "address": "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
        "lat": 50.3717,
        "lng": -4.1386,
    },
    {
        "index": 2,
        "address": "Plymouth Market, Cornwall Street, Plymouth, PL1 1PS",
        "lat": 50.3712,
        "lng": -4.1439,
    },
    {
        "index": 3,
        "address": "Royal William Yard, Plymouth, PL1 3RP",
        "lat": 50.3645,
        "lng": -4.1670,
    },
]


DEMO_DISTANCE_MATRIX_KM = np.array(
    [
        [0.0, 1.1, 1.2, 3.4],
        [1.1, 0.0, 0.8, 3.1],
        [1.2, 0.8, 0.0, 2.7],
        [3.4, 3.1, 2.7, 0.0],
    ],
    dtype=float,
)


def serialise_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def first_number(*values: Any) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def route_distance(order: list[int], matrix: np.ndarray) -> float:
    return calculate_path_distance(order, matrix)


def build_demo_export() -> dict[str, Any]:
    matrix = DEMO_DISTANCE_MATRIX_KM
    input_order = list(range(len(DEMO_STOPS)))
    nearest_order = nearest_neighbour_route(matrix)
    exact_order = brute_force_route(matrix)

    input_distance = route_distance(input_order, matrix)
    nearest_distance = route_distance(nearest_order, matrix)
    exact_distance = route_distance(exact_order, matrix)
    distance_saved = round(max(input_distance - exact_distance, 0.0), 2)

    return {
        "schema_version": "quantaroute.route_problem_export.v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "problem_id": "demo-plymouth-route-problem",
        "problem_label": "Plymouth demo route problem",
        "source": "demo",
        "storage_backend": None,
        "problem_type": "delivery_order_only",
        "units": "km",
        "start_address": DEMO_STOPS[0]["address"],
        "end_address": "",
        "input_stops": [stop["address"] for stop in DEMO_STOPS],
        "ordered_stops": [DEMO_STOPS[index]["address"] for index in exact_order],
        "stops": DEMO_STOPS,
        "distance_matrix_km": matrix.tolist(),
        "baseline_algorithm_used": "exact brute force",
        "baseline_orders": {
            "input_order": input_order,
            "nearest_neighbour": nearest_order,
            "production_selected": exact_order,
        },
        "original_distance_km": input_distance,
        "nearest_neighbour_distance_km": nearest_distance,
        "optimised_distance_km": exact_distance,
        "distance_saved_km": distance_saved,
        "estimated_saving_percent": estimate_fuel_saving(input_distance, exact_distance),
        "notes": [
            PRODUCTION_BASELINE_NOTE,
            "Demo matrix is static and approximate so the script can run without database, secrets, or external APIs.",
        ],
    }


def build_saved_route_export(route_id: int) -> dict[str, Any]:
    route = get_route_by_id(route_id)
    if route is None:
        raise SystemExit(f"Route {route_id} was not found in the configured storage backend.")

    original_distance = first_number(
        route.get("original_distance_km"),
        route.get("original_order_distance_km"),
        route.get("naive_distance_km"),
    )
    optimised_distance = first_number(
        route.get("optimised_distance_km"),
        route.get("final_selected_distance_km"),
        route.get("total_distance_km"),
    )
    distance_saved = route.get("distance_saved_km")
    if distance_saved is None:
        distance_saved = round(max(original_distance - optimised_distance, 0.0), 2)

    original_stops = route.get("original_addresses") or []
    ordered_stops = route.get("ordered_stops") or route.get("ordered_addresses") or []

    return {
        "schema_version": "quantaroute.route_problem_export.v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "problem_id": f"route-{route_id}",
        "problem_label": f"Saved route {route_id}",
        "source": "route_history",
        "storage_backend": "postgres" if using_postgres() else "sqlite",
        "problem_type": "saved_route_summary",
        "units": "km",
        "route_id": route_id,
        "created_at": serialise_value(route.get("created_at")),
        "start_address": route.get("start_address") or "",
        "end_address": route.get("end_address") or "",
        "input_stops": original_stops,
        "ordered_stops": ordered_stops,
        "stops": [
            {"index": index, "address": address}
            for index, address in enumerate(original_stops or ordered_stops)
        ],
        "distance_matrix_km": None,
        "baseline_algorithm_used": route.get("algorithm_used") or "not recorded",
        "baseline_orders": {
            "input_order": list(range(len(original_stops))),
            "production_selected": None,
        },
        "original_distance_km": original_distance,
        "nearest_neighbour_distance_km": first_number(route.get("nearest_neighbour_distance_km")),
        "optimised_distance_km": optimised_distance,
        "distance_saved_km": first_number(distance_saved),
        "estimated_saving_percent": first_number(
            route.get("estimated_saving_percent"),
            route.get("fuel_saving_percent_vs_original"),
            route.get("fuel_saving_percent"),
        ),
        "google_maps_url": route.get("google_maps_url") or route.get("maps_url") or "",
        "notes": [
            PRODUCTION_BASELINE_NOTE,
            "Saved route history does not currently store the original distance matrix, so distance_matrix_km is null.",
            "Use --demo for a complete static matrix export, or add future matrix capture behind an experimental flag.",
        ],
    }


def write_or_print_export(payload: dict[str, Any], out_path: Path | None) -> None:
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    if out_path is None:
        print(encoded)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(encoded + "\n", encoding="utf-8")
    print(f"Wrote route problem export: {out_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export an offline QuantaRoute route problem JSON for solver experiments."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Export a static Plymouth demo route problem. This is the default when --route-id is omitted.",
    )
    parser.add_argument(
        "--route-id",
        type=int,
        default=None,
        help="Export metadata for a saved route history record. The saved matrix is not available.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output JSON path. Prints to stdout when omitted.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.route_id is not None and args.demo:
        raise SystemExit("Use either --demo or --route-id, not both.")

    payload = (
        build_saved_route_export(args.route_id)
        if args.route_id is not None
        else build_demo_export()
    )
    write_or_print_export(payload, args.out)


if __name__ == "__main__":
    main()
