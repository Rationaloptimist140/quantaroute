import csv
import json

import database
from scripts.export_route_history import build_export_records, export_route_history


def test_route_history_export_writes_json_and_csv(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "export-history.db")
    database.init_db(force=True)

    route_id = database.save_route(
        "Backup Test Driver",
        {
            "ordered_addresses": [
                "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
                "Royal William Yard, Plymouth, PL1 3RP",
            ],
            "start_address": "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
            "end_address": "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
            "return_to_start": False,
            "original_distance_km": 12.5,
            "optimised_distance_km": 9.75,
            "estimated_saving_percent": 22.0,
            "maps_url": "https://www.google.com/maps/dir/Plymouth/Stops",
            "whatsapp_message": "Hi Driver! Your route is ready.",
            "stops_count": 2,
        },
        source="api",
        vehicle="van",
        optimise_for="distance",
        original_addresses=[
            "Royal William Yard, Plymouth, PL1 3RP",
            "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
        ],
        whatsapp_message="Hi Driver! Your route is ready.",
    )

    routes = database.get_route_history_for_export()
    records = build_export_records(routes, base_url="https://example.test")

    assert records[0]["route_id"] == route_id
    assert records[0]["original_stops"][0].startswith("Royal William Yard")
    assert records[0]["ordered_stops"][0].startswith("Drake Circus")
    assert records[0]["original_distance_km"] == 12.5
    assert records[0]["optimised_distance_km"] == 9.75
    assert records[0]["distance_saved_km"] == 2.75
    assert records[0]["estimated_saving_percent"] == 22.0
    assert records[0]["google_maps_url"].startswith("https://www.google.com/maps/dir/")
    assert records[0]["whatsapp_message"].startswith("Hi Driver!")
    assert records[0]["route_sheet_url"] == f"https://example.test/route-sheet/{route_id}"
    assert records[0]["source"] == "api"
    assert records[0]["vehicle"] == "van"
    assert records[0]["optimise_for"] == "distance"

    result = export_route_history(
        output_dir=tmp_path / "exports",
        export_format="both",
        base_url="https://example.test",
    )

    assert result["count"] == 1
    json_path = next(path for path in result["paths"] if path.suffix == ".json")
    csv_path = next(path for path in result["paths"] if path.suffix == ".csv")

    json_records = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_records[0]["route_sheet_url"] == f"https://example.test/route-sheet/{route_id}"

    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_records = list(csv.DictReader(handle))

    assert csv_records[0]["route_id"] == str(route_id)
    assert "Royal William Yard" in csv_records[0]["original_stops"]
    assert csv_records[0]["route_sheet_url"] == f"https://example.test/route-sheet/{route_id}"
