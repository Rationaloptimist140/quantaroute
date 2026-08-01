"""Tests for the standard CSV upload normalization logic.

Covers Format A (Property Name,Address,Postcode,Type), Format B
(Postcode,Number - the recommended public standard), the legacy fallback
for CSVs that don't match either format's headers, and the stop_count
defaulting rule for Format B.
"""

from fastapi.testclient import TestClient

import database
from backend import main
from backend.main import app, parse_csv_rows_normalised


client = TestClient(app)


FORMAT_A_CSV = (
    "Property Name,Address,Postcode,Type\n"
    "Old School Building,1 Naoroji Street Clerkenwell,WC1X 0GB,Office\n"
    "Riverside House,22 Bankside,SE1 9JE,Retail\n"
)

FORMAT_B_CSV = (
    "Postcode,Number\n"
    "WC1X 0GB,1\n"
    "SE1 9JE,3\n"
)

UNSUPPORTED_HEADERS_CSV = (
    "Foo,Bar\n"
    "1,2\n"
    "3,4\n"
)


def test_parse_format_a_builds_address_from_address_and_postcode():
    rows = parse_csv_rows_normalised(FORMAT_A_CSV)

    assert len(rows) == 2
    assert rows[0] == {
        "address": "1 Naoroji Street Clerkenwell, WC1X 0GB",
        "stop_count": 1,
    }
    assert rows[1] == {
        "address": "22 Bankside, SE1 9JE",
        "stop_count": 1,
    }


def test_parse_format_b_uses_postcode_and_number():
    rows = parse_csv_rows_normalised(FORMAT_B_CSV)

    assert rows == [
        {"address": "WC1X 0GB", "stop_count": 1},
        {"address": "SE1 9JE", "stop_count": 3},
    ]


def test_format_b_blank_or_invalid_number_defaults_to_one():
    csv_text = (
        "Postcode,Number\n"
        "WC1X 0GB,\n"          # blank
        "SE1 9JE,not-a-number\n"  # invalid
        "PL1 2AB,0\n"           # non-positive, also defaults
        "PL4 6AB,5\n"           # valid, kept as-is
    )

    rows = parse_csv_rows_normalised(csv_text)

    assert rows == [
        {"address": "WC1X 0GB", "stop_count": 1},
        {"address": "SE1 9JE", "stop_count": 1},
        {"address": "PL1 2AB", "stop_count": 1},
        {"address": "PL4 6AB", "stop_count": 5},
    ]


def test_format_detection_is_header_based_not_value_guessing():
    """Column order or casing/whitespace in the header row shouldn't matter,
    but the values in the rows must never be used to decide the format."""
    csv_text = (
        " number , POSTCODE \n"
        "1,WC1X 0GB\n"
    )

    rows = parse_csv_rows_normalised(csv_text)

    assert rows == [{"address": "WC1X 0GB", "stop_count": 1}]


def test_legacy_fallback_still_works_for_unrecognised_header_shapes():
    """CSVs that don't match either new format's headers exactly must keep
    working via the existing legacy parser (backward compatibility)."""
    csv_text = (
        "Stop Number,Business Name,Address,Postcode,Order Details\n"
        "1,Cosy Club,11 Bretonside Plymouth,PL4 0FE,5 boxes\n"
        "2,Monty's Cafe,13 The Barbican Plymouth,PL1 2LS,coffee\n"
    )

    rows = parse_csv_rows_normalised(csv_text)

    assert len(rows) == 2
    assert all(row["stop_count"] == 1 for row in rows)
    assert all(row["address"] for row in rows)


def test_legacy_fallback_still_works_for_headerless_address_list():
    csv_text = "Plymouth PL1\nExeter EX1\nBristol BS1\n"

    rows = parse_csv_rows_normalised(csv_text)

    assert rows == [
        {"address": "Plymouth PL1", "stop_count": 1},
        {"address": "Exeter EX1", "stop_count": 1},
        {"address": "Bristol BS1", "stop_count": 1},
    ]


def test_upload_csv_endpoint_accepts_format_a(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "csv-format-a.db")
    database.init_db(force=True)

    async def fake_optimise_route(**_kwargs):
        return {
            "optimised_order": [0, 1],
            "ordered_addresses": [
                "1 Naoroji Street Clerkenwell, WC1X 0GB",
                "22 Bankside, SE1 9JE",
            ],
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
            "stops_count": 2,
            "geocoded_count": 2,
            "failed_addresses": [],
        }

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", FORMAT_A_CSV, "text/csv")},
    )

    assert response.status_code == 200


def test_upload_csv_endpoint_accepts_format_b(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "csv-format-b.db")
    database.init_db(force=True)

    async def fake_optimise_route(**_kwargs):
        return {
            "optimised_order": [0, 1],
            "ordered_addresses": ["WC1X 0GB", "SE1 9JE"],
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
            "stops_count": 2,
            "geocoded_count": 2,
            "failed_addresses": [],
        }

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", FORMAT_B_CSV, "text/csv")},
    )

    assert response.status_code == 200


def test_upload_csv_endpoint_rejects_unsupported_headers_with_clear_message():
    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", UNSUPPORTED_HEADERS_CSV, "text/csv")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Postcode,Number" in detail
    assert "Property Name,Address,Postcode,Type" in detail
