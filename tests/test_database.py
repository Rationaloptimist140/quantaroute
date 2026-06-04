import database


def sample_route_result() -> dict:
    return {
        "ordered_addresses": [
            "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
            "Royal William Yard, Plymouth, PL1 3RP",
        ],
        "start_address": "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
        "end_address": "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
        "return_to_start": False,
        "total_distance_km": 9.2,
        "naive_distance_km": 10.1,
        "fuel_saving_percent": 8.9,
        "original_order_distance_km": 10.1,
        "nearest_neighbour_distance_km": 9.5,
        "final_selected_distance_km": 9.2,
        "fuel_saving_percent_vs_original": 8.9,
        "maps_url": "https://www.google.com/maps/dir/Plymouth/Stops",
        "whatsapp_url": "https://wa.me/?text=Route",
        "stops_count": 2,
    }


def test_sqlite_fallback_route_history_round_trip(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quantaroute-test.db")
    database.init_db(force=True)

    route_id = database.save_route(
        "API Agent",
        sample_route_result(),
        source="api",
        vehicle="van",
        optimise_for="distance",
        original_addresses=[
            "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
            "Royal William Yard, Plymouth, PL1 3RP",
        ],
        warnings=["Distance estimates compare route candidates against the address order entered."],
        whatsapp_message="Hi Driver! Your optimised route is ready.",
    )

    route = database.get_route_by_id(route_id)

    assert route is not None
    assert route["id"] == route_id
    assert route["source"] == "api"
    assert route["vehicle"] == "van"
    assert route["optimise_for"] == "distance"
    assert route["original_addresses"][0].startswith("Drake Circus")
    assert route["ordered_stops"][1].startswith("Royal William Yard")
    assert route["original_distance_km"] == 10.1
    assert route["optimised_distance_km"] == 9.2
    assert route["distance_saved_km"] == 0.9
    assert route["estimated_saving_percent"] == 8.9
    assert route["google_maps_url"].startswith("https://www.google.com/maps/dir/")
    assert route["whatsapp_message"].startswith("Hi Driver!")
    assert route["warnings"]

    history = database.get_recent_routes(limit=1)
    assert history[0]["id"] == route_id


def test_api_key_creation_stores_hash_only(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "api-key-storage.db")
    database.init_db(force=True)

    created = database.create_api_key("Test Client", monthly_limit=25)
    raw_key = created["api_key"]
    key_hash = database.hash_api_key(raw_key)

    with database.get_sqlite_connection() as conn:
        row = conn.execute(
            f"SELECT key_hash, label, monthly_limit FROM {database.API_KEYS_TABLE} WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()

    assert row is not None
    assert row["key_hash"] == key_hash
    assert row["key_hash"] != raw_key
    assert row["label"] == "Test Client"
    assert row["monthly_limit"] == 25
