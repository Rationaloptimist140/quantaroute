from fastapi.testclient import TestClient

import database
from backend import main
from backend.main import app
from database import create_api_key, get_route_by_id, get_usage_events, save_route


client = TestClient(app)


def sample_payload() -> dict:
    return {
        "start": "Plymouth, UK",
        "stops": [
            "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
            "Royal William Yard, Plymouth, PL1 3RP",
            "Plymouth Market, Cornwall Street, Plymouth, PL1 1PS",
            "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
        ],
        "end": "Plymouth, UK",
        "vehicle": "van",
        "optimise_for": "distance",
    }


def fake_route_result() -> dict:
    return {
        "optimised_order": [0, 1, 2, 3],
        "ordered_addresses": [
            "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
            "Royal William Yard, Plymouth, PL1 3RP",
            "Plymouth Market, Cornwall Street, Plymouth, PL1 1PS",
            "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
        ],
        "start_address": "Plymouth, UK",
        "return_to_start": False,
        "end_address": "Plymouth, UK",
        "total_distance_km": 10.0,
        "naive_distance_km": 12.5,
        "fuel_saving_percent": 20.0,
        "original_order_distance_km": 12.5,
        "nearest_neighbour_distance_km": 11.0,
        "final_selected_distance_km": 10.0,
        "fuel_saving_percent_vs_original": 20.0,
        "maps_url": "https://www.google.com/maps/dir/Plymouth/Stop",
        "whatsapp_url": "https://wa.me/?text=Driver%20route",
        "algorithm_used": "exact brute force",
        "stops_count": 4,
        "geocoded_count": 4,
        "failed_addresses": [],
    }


def test_health_includes_safe_storage_diagnostics():
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["build"] == "health-storage-backend-2026-06-11"
    assert data["storage_backend"] in {"postgres", "sqlite"}
    assert isinstance(data["database_configured"], bool)
    assert isinstance(data["route_history_available"], bool)
    assert isinstance(data["api_keys_available"], bool)
    assert isinstance(data["usage_tracking_available"], bool)
    assert "DATABASE_URL" not in data


def test_public_api_success(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "public-api-no-key.db")
    database.init_db(force=True)

    async def fake_optimise_route(**_kwargs):
        return fake_route_result()

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)
    response = client.post("/api/optimise-route", json=sample_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["input_stop_count"] == 4
    assert data["google_maps_url"].startswith("https://www.google.com/maps/dir/")
    assert "Tap to open in Google Maps" in data["whatsapp_message"]
    assert data["route_sheet_url"].startswith("http://testserver/route-sheet/")
    assert data["algorithm_used"] == "exact brute force"
    assert data["api_client"] is None
    events = get_usage_events(limit=1)
    assert events[0]["source"] == "public_api"
    assert events[0]["endpoint"] == "/api/optimise-route"
    assert events[0]["status"] == "success"
    assert events[0]["api_key_id"] is None


def test_public_api_with_valid_api_key_tracks_usage_and_route_source(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "api-key-test.db")
    database.init_db(force=True)

    async def fake_optimise_route(**_kwargs):
        return fake_route_result()

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)
    api_key = create_api_key(
        "Courier Bot",
        monthly_limit=1000,
        source_label="courier_bot",
    )

    response = client.post(
        "/api/optimise-route",
        json=sample_payload(),
        headers={"X-API-Key": api_key["api_key"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["api_client"] == {
        "label": "Courier Bot",
        "usage_count_current_month": 1,
        "monthly_limit": 1000,
    }

    route_id = int(data["route_sheet_url"].rstrip("/").rsplit("/", 1)[-1])
    route = get_route_by_id(route_id)
    assert route is not None
    assert route["source"] == "api_key:courier_bot"
    events = get_usage_events(limit=1)
    assert events[0]["route_id"] == route_id
    assert events[0]["api_key_id"] == api_key["id"]
    assert events[0]["source"] == "api_key:courier_bot"
    assert events[0]["stops_count"] == 4
    assert events[0]["distance_saved_km"] == 2.5
    assert events[0]["estimated_saving_percent"] == 20.0

    second_response = client.post(
        "/api/optimise-route",
        json=sample_payload(),
        headers={"X-API-Key": api_key["api_key"]},
    )
    assert second_response.status_code == 200
    assert second_response.json()["api_client"]["usage_count_current_month"] == 2


def test_public_api_invalid_api_key_rejected(monkeypatch):
    async def fake_optimise_route(**_kwargs):
        raise AssertionError("optimise_route should not run for invalid API keys")

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    response = client.post(
        "/api/optimise-route",
        json=sample_payload(),
        headers={"X-API-Key": "qr_not_a_real_key"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_API_KEY"
    assert data["error"]["message"] == "Invalid or inactive API key."


def test_public_api_inactive_api_key_rejected(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "inactive-key-test.db")
    database.init_db(force=True)
    api_key = create_api_key("Inactive Client")
    key_hash = database.hash_api_key(api_key["api_key"])
    with database.get_sqlite_connection() as conn:
        conn.execute(
            f"UPDATE {database.API_KEYS_TABLE} SET is_active = 0 WHERE key_hash = ?",
            (key_hash,),
        )
        conn.commit()

    response = client.post(
        "/api/optimise-route",
        json=sample_payload(),
        headers={"X-API-Key": api_key["api_key"]},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_API_KEY"
    assert data["error"]["message"] == "Invalid or inactive API key."


def test_public_api_monthly_limit_exceeded(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "monthly-limit-test.db")
    database.init_db(force=True)

    async def fake_optimise_route(**_kwargs):
        return fake_route_result()

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)
    api_key = create_api_key("Limited Client", monthly_limit=1)

    first_response = client.post(
        "/api/optimise-route",
        json=sample_payload(),
        headers={"X-API-Key": api_key["api_key"]},
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/api/optimise-route",
        json=sample_payload(),
        headers={"X-API-Key": api_key["api_key"]},
    )

    assert second_response.status_code == 429
    data = second_response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "MONTHLY_LIMIT_EXCEEDED"
    assert data["error"]["message"] == "This API key has reached its monthly route limit."


def test_bad_json_returns_structured_validation_error():
    response = client.post(
        "/api/optimise-route",
        data="{",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_REQUEST"


def test_over_20_stops_rejected():
    payload = sample_payload()
    payload["stops"] = [f"Stop {index}, Plymouth" for index in range(21)]

    response = client.post("/api/optimise-route", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "TOO_MANY_STOPS"


def test_extremely_long_address_rejected():
    payload = sample_payload()
    payload["stops"][0] = "A" * 241

    response = client.post("/api/optimise-route", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "ADDRESS_TOO_LONG"


def test_duplicate_only_stop_list_rejected():
    payload = sample_payload()
    payload["stops"] = ["Royal William Yard, Plymouth", "Royal William Yard, Plymouth"]

    response = client.post("/api/optimise-route", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_STOPS"


def test_failed_geocoding_returns_clear_error(monkeypatch):
    async def fake_optimise_route(**_kwargs):
        raise main.RouteGeocodingError(["Bad Stop"])

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)
    response = client.post("/api/optimise-route", json=sample_payload())

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "GEOCODING_FAILED"
    assert data["error"]["message"] == main.GEOCODING_HELP_MESSAGE
    assert data["error"]["details"] == [
        {
            "address": "Bad Stop",
            "message": main.GEOCODING_HELP_MESSAGE,
        }
    ]


def test_llms_txt_works():
    response = client.get("/llms.txt")

    assert response.status_code == 200
    assert "POST /api/optimise-route" in response.text


def test_openapi_includes_public_api_route():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/optimise-route" in response.text
    assert "X-API-Key" in response.text


def test_developers_page_is_served():
    response = client.get("/developers.html")

    assert response.status_code == 200
    assert "optimise_delivery_route" in response.text
    assert "POST /api/optimise-route" in response.text


def test_route_sheet_endpoint_renders_saved_route():
    route_id = save_route("Test Driver", fake_route_result())

    response = client.get(f"/route-sheet/{route_id}")

    assert response.status_code == 200
    assert "QuantaRoute Driver Route Sheet" in response.text
    assert "Royal William Yard, Plymouth, PL1 3RP" in response.text
    assert "https://www.google.com/maps/dir/Plymouth/Stop" in response.text
    assert "Original" in response.text
    assert "Optimised" in response.text
    assert "Route method" in response.text
    assert "exact brute force" in response.text


def test_route_sheet_formats_postcode_start_and_missing_end():
    result = fake_route_result()
    result["start_address"] = "pl1 2hf"
    result["end_address"] = ""
    result["return_to_start"] = False
    route_id = save_route("Test Driver", result)

    response = client.get(f"/route-sheet/{route_id}")

    assert response.status_code == 200
    assert "<strong>Start:</strong> PL1 2HF" in response.text
    assert "End:</strong> Final delivery stop — no return address selected" in response.text


def test_recent_routes_endpoint_returns_route_summary(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "recent-routes.db")
    database.init_db(force=True)
    route_id = save_route("Test Driver", fake_route_result())

    response = client.get("/api/routes/recent")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    route = data[0]
    assert route["id"] == route_id
    assert route["created_at"]
    assert route["start_address"] == "Plymouth, UK"
    assert route["end_address"] == "Plymouth, UK"
    assert route["original_distance_km"] == 12.5
    assert route["optimised_distance_km"] == 10.0
    assert route["distance_saved_km"] == 2.5
    assert route["estimated_saving_percent"] == 20.0
    assert route["route_sheet_url"] == f"http://testserver/route-sheet/{route_id}"
