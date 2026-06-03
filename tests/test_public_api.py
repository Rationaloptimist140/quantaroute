from fastapi.testclient import TestClient

from backend import main
from backend.main import app


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
        "stops_count": 4,
        "geocoded_count": 4,
        "failed_addresses": [],
    }


def test_public_api_success(monkeypatch):
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


def test_developers_page_is_served():
    response = client.get("/developers.html")

    assert response.status_code == 200
    assert "optimise_delivery_route" in response.text
    assert "POST /api/optimise-route" in response.text
