"""Tests for the private product-analytics dashboard (GET /admin/metrics)
and the underlying analytics_events tracking.

Covers: event recording for successful/failed routes and each input method,
admin auth (unauthenticated rejection + no-credentials-configured 404),
that dashboard responses never contain raw addresses, date filters, and the
empty-data state.
"""

import database
from backend import main
from backend.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def init_test_db(monkeypatch, tmp_path, name):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / name)
    database.init_db(force=True)


def fake_result(addresses):
    return {
        "optimised_order": list(range(len(addresses))),
        "ordered_addresses": addresses,
        "start_address": None,
        "return_to_start": False,
        "end_address": None,
        "total_distance_km": 5.0,
        "naive_distance_km": 5.0,
        "fuel_saving_percent": 0.0,
        "original_order_distance_km": 5.0,
        "nearest_neighbour_distance_km": 5.0,
        "final_selected_distance_km": 5.0,
        "fuel_saving_percent_vs_original": 0.0,
        "maps_url": "https://www.google.com/maps/dir/Test",
        "whatsapp_url": "https://wa.me/?text=Test",
        "algorithm_used": "exact brute force",
        "stops_count": len(addresses),
        "geocoded_count": len(addresses),
        "failed_addresses": [],
    }


def test_successful_route_completion_records_route_completed(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-completed.db")

    async def fake_optimise_route(**_kwargs):
        return fake_result(["Plymouth PL1", "Exeter EX1"])

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    response = client.post(
        "/quantum/route-optimise",
        json={"addresses": ["Plymouth PL1", "Exeter EX1"], "driver_name": "Driver"},
    )
    assert response.status_code == 200

    events = database.get_analytics_events_since()
    completed = [e for e in events if e["event_name"] == "route_completed"]
    assert len(completed) == 1
    assert completed[0]["input_method"] == "plain_addresses"
    assert completed[0]["stop_count"] == 2
    assert completed[0]["duration_ms"] is not None


def test_failed_route_records_route_failed(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-failed.db")

    async def fake_optimise_route(**_kwargs):
        # Use main.RouteGeocodingError (not a fresh import of
        # backend.services.route_builder.RouteGeocodingError) - main.py
        # imports it via services.route_builder (sys.path trick), so a
        # separately-imported class object would fail main.py's
        # `except RouteGeocodingError` identity check and fall through to
        # `except ValueError` instead, misclassifying this test's failure.
        raise main.RouteGeocodingError(["Nowhere Land"])

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    response = client.post(
        "/quantum/route-optimise",
        json={"addresses": ["Nowhere Land", "Somewhere Else"], "driver_name": "Driver"},
    )
    assert response.status_code == 400

    events = database.get_analytics_events_since()
    event_names = {e["event_name"] for e in events}
    assert "route_failed" in event_names
    assert "geocoding_failed" in event_names
    # geocoding_failed must not also be misfiled as routing_failed
    assert "routing_failed" not in event_names


def test_csv_upload_records_detected_format(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-csv-upload.db")

    async def fake_optimise_route(**_kwargs):
        return fake_result(["WC1X 0GB", "SE1 9JE"])

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", "Postcode,Number\nWC1X 0GB,1\nSE1 9JE,3\n", "text/csv")},
    )
    assert response.status_code == 200

    events = database.get_analytics_events_since()
    input_events = [e for e in events if e["event_name"] == "input_submitted"]
    assert any(
        e["input_method"] == "csv_upload" and e["csv_format"] == "postcode_number"
        for e in input_events
    )


def test_csv_paste_records_detected_format(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-csv-paste.db")

    async def fake_optimise_route(**_kwargs):
        return fake_result(["WC1X 0GB", "SE1 9JE"])

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    # The frontend always names the virtual pasted-CSV file exactly this -
    # that's how the backend tells csv_upload and csv_paste apart.
    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("pasted-addresses.csv", "Postcode,Number\nWC1X 0GB,1\nSE1 9JE,3\n", "text/csv")},
    )
    assert response.status_code == 200

    events = database.get_analytics_events_since()
    input_events = [e for e in events if e["event_name"] == "input_submitted"]
    assert any(
        e["input_method"] == "csv_paste" and e["csv_format"] == "postcode_number"
        for e in input_events
    )


def test_plain_addresses_record_plain_addresses(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-plain.db")

    async def fake_optimise_route(**_kwargs):
        return fake_result(["Plymouth PL1", "Exeter EX1"])

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    client.post(
        "/quantum/route-optimise",
        json={"addresses": ["Plymouth PL1", "Exeter EX1"], "driver_name": "Driver"},
    )

    events = database.get_analytics_events_since()
    input_events = [e for e in events if e["event_name"] == "input_submitted"]
    assert any(e["input_method"] == "plain_addresses" for e in input_events)


def test_unauthenticated_admin_access_is_rejected(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-auth.db")
    monkeypatch.setenv("ADMIN_METRICS_USER", "owner")
    monkeypatch.setenv("ADMIN_METRICS_PASSWORD", "s3cret")

    no_auth = client.get("/admin/metrics")
    assert no_auth.status_code == 401

    wrong_auth = client.get("/admin/metrics", auth=("owner", "wrong-password"))
    assert wrong_auth.status_code == 401

    correct_auth = client.get("/admin/metrics", auth=("owner", "s3cret"))
    assert correct_auth.status_code == 200


def test_admin_dashboard_is_404_when_credentials_not_configured(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-no-creds.db")
    monkeypatch.delenv("ADMIN_METRICS_USER", raising=False)
    monkeypatch.delenv("ADMIN_METRICS_PASSWORD", raising=False)

    response = client.get("/admin/metrics")
    assert response.status_code == 404


def test_dashboard_data_contains_no_raw_addresses(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-no-pii.db")
    monkeypatch.setenv("ADMIN_METRICS_USER", "owner")
    monkeypatch.setenv("ADMIN_METRICS_PASSWORD", "s3cret")

    secret_addresses = ["1 Secret Street, London", "42 Hidden Lane, Bristol"]

    async def fake_optimise_route(**_kwargs):
        return fake_result(secret_addresses)

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    client.post(
        "/quantum/route-optimise",
        json={"addresses": secret_addresses, "driver_name": "Driver"},
    )

    data_response = client.get("/admin/metrics/data?range=all", auth=("owner", "s3cret"))
    assert data_response.status_code == 200
    assert "Secret Street" not in data_response.text
    assert "Hidden Lane" not in data_response.text

    page_response = client.get("/admin/metrics", auth=("owner", "s3cret"))
    assert page_response.status_code == 200
    assert "Secret Street" not in page_response.text
    assert "Hidden Lane" not in page_response.text

    csv_response = client.get("/admin/metrics/export.csv?range=all", auth=("owner", "s3cret"))
    assert csv_response.status_code == 200
    assert "Secret Street" not in csv_response.text
    assert "Hidden Lane" not in csv_response.text


def test_date_filters_work(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-filters.db")
    monkeypatch.setenv("ADMIN_METRICS_USER", "owner")
    monkeypatch.setenv("ADMIN_METRICS_PASSWORD", "s3cret")

    database.record_analytics_event(
        "route_completed", stop_count=3, duration_ms=100, app_build="test",
    )

    for range_key in ["24h", "7d", "30d", "all"]:
        response = client.get(f"/admin/metrics/data?range={range_key}", auth=("owner", "s3cret"))
        assert response.status_code == 200
        data = response.json()
        assert data["range"] == range_key
        assert data["summary"]["routes_completed"] >= 1


def test_empty_data_returns_valid_empty_dashboard(monkeypatch, tmp_path):
    init_test_db(monkeypatch, tmp_path, "analytics-empty.db")
    monkeypatch.setenv("ADMIN_METRICS_USER", "owner")
    monkeypatch.setenv("ADMIN_METRICS_PASSWORD", "s3cret")

    response = client.get("/admin/metrics/data?range=all", auth=("owner", "s3cret"))
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_events"] == 0
    assert data["summary"]["routes_completed"] == 0
    assert data["summary"]["route_success_rate_percent"] is None
    assert data["recent_events"] == []

    page_response = client.get("/admin/metrics", auth=("owner", "s3cret"))
    assert page_response.status_code == 200
