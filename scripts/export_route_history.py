"""Export QuantaRoute route history to JSON and CSV.

The script uses the same storage adapter as the FastAPI app:
DATABASE_URL/Postgres when configured, otherwise local SQLite.
"""

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import get_route_history_for_export, using_postgres  # noqa: E402


EXPORT_COLUMNS = [
    "route_id",
    "created_at",
    "start_address",
    "end_address",
    "original_stops",
    "ordered_stops",
    "original_distance_km",
    "optimised_distance_km",
    "distance_saved_km",
    "estimated_saving_percent",
    "google_maps_url",
    "whatsapp_message",
    "route_sheet_url",
    "source",
    "vehicle",
    "optimise_for",
]


def serialise_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def csv_value(value: Any) -> str:
    value = serialise_value(value)
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def first_number(*values: Any) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def build_route_sheet_url(route_id: Any, base_url: str) -> str:
    if not route_id:
        return ""
    clean_base_url = str(base_url or "").strip().rstrip("/")
    if not clean_base_url:
        return ""
    return f"{clean_base_url}/route-sheet/{route_id}"


def build_export_records(
    routes: list[dict[str, Any]],
    *,
    base_url: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for route in routes:
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

        record = {
            "route_id": route.get("id"),
            "created_at": serialise_value(route.get("created_at")),
            "start_address": route.get("start_address") or "",
            "end_address": route.get("end_address") or "",
            "original_stops": route.get("original_addresses") or [],
            "ordered_stops": route.get("ordered_stops")
            or route.get("ordered_addresses")
            or [],
            "original_distance_km": original_distance,
            "optimised_distance_km": optimised_distance,
            "distance_saved_km": first_number(distance_saved),
            "estimated_saving_percent": first_number(
                route.get("estimated_saving_percent"),
                route.get("fuel_saving_percent_vs_original"),
                route.get("fuel_saving_percent"),
            ),
            "google_maps_url": route.get("google_maps_url")
            or route.get("maps_url")
            or "",
            "whatsapp_message": route.get("whatsapp_message") or "",
            "route_sheet_url": build_route_sheet_url(route.get("id"), base_url),
            "source": route.get("source") or "",
            "vehicle": route.get("vehicle") or "",
            "optimise_for": route.get("optimise_for") or "",
        }
        records.append(record)
    return records


def write_json(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow({column: csv_value(record.get(column)) for column in EXPORT_COLUMNS})


def export_route_history(
    *,
    output_dir: Path,
    export_format: str = "both",
    base_url: str = "https://quantaroute.co.uk",
    limit: int | None = None,
) -> dict[str, Any]:
    routes = get_route_history_for_export(limit=limit)
    records = build_export_records(routes, base_url=base_url)

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    stem = f"quantaroute_route_history_{timestamp}"
    written_paths: list[Path] = []

    if export_format in {"json", "both"}:
        json_path = output_dir / f"{stem}.json"
        write_json(json_path, records)
        written_paths.append(json_path)

    if export_format in {"csv", "both"}:
        csv_path = output_dir / f"{stem}.csv"
        write_csv(csv_path, records)
        written_paths.append(csv_path)

    return {
        "count": len(records),
        "paths": written_paths,
        "storage": "Postgres DATABASE_URL" if using_postgres() else "local SQLite",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export QuantaRoute route history.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "exports",
        help="Directory where JSON/CSV backup files will be written.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "both"],
        default="both",
        help="Export JSON, CSV, or both.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("QUANTAROUTE_BASE_URL", "https://quantaroute.co.uk"),
        help="Base URL used to build route_sheet_url values.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of most-recent routes to export.",
    )
    args = parser.parse_args()

    result = export_route_history(
        output_dir=args.output_dir,
        export_format=args.format,
        base_url=args.base_url,
        limit=args.limit,
    )

    print("QuantaRoute route history exported.")
    print(f"Storage: {result['storage']}")
    print(f"Routes exported: {result['count']}")
    for path in result["paths"]:
        print(f"Wrote: {path}")


if __name__ == "__main__":
    main()
