"""Tests for the standard CSV upload normalization logic.

Covers three documented formats, tried in this order:
  - Format A: Property Name,Address,Postcode,Type (header-based)
  - Format B: Postcode,Number - the recommended public standard (header-based)
  - Format C: headerless two-column compatibility format, e.g. "WC1X 0GB,1"
    with no header row at all - column 1 is the address/postcode, column 2
    is stop_count, with no ignore-cell heuristics applied
and the legacy fallback for anything that matches none of the three.
"""

from fastapi.testclient import TestClient

import database
from backend import main
from backend.main import app, classify_csv_format, parse_csv_rows_normalised


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

# Format C: headerless two-column compatibility format. No header row -
# every row has exactly two columns, so column 1 is taken directly as the
# address/postcode (bypassing the legacy is_postcode_only/is_ignored_csv_cell
# heuristics that would otherwise discard a bare postcode) and column 2 is
# stop_count.
FORMAT_C_CSV = (
    "WC1X 0GB,1\n"
    "EC3M 1EB,20\n"
    "EC2A 2EG,12\n"
)

# "Qty,Notes" is recognised as a header row by the legacy parser (it knows
# the word "notes"), but has no business/address-shaped column and every
# data cell is a bare number - so it also yields zero addresses via the
# legacy fallback, giving a genuine "nothing could be read" case. Being
# recognised as a header row also keeps it out of the Format C path, even
# though the data rows below it have exactly two columns.
UNSUPPORTED_HEADERS_CSV = (
    "Qty,Notes\n"
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


def test_parse_format_c_headerless_two_column_compatibility():
    """The exact shape reported as 'working in production': a bare postcode
    and a number on each line, with no header row at all. This must not be
    swallowed by the legacy is_postcode_only/is_ignored_csv_cell heuristics,
    which would otherwise treat every cell as non-address and drop the row."""
    rows = parse_csv_rows_normalised(FORMAT_C_CSV)

    assert rows == [
        {"address": "WC1X 0GB", "stop_count": 1},
        {"address": "EC3M 1EB", "stop_count": 20},
        {"address": "EC2A 2EG", "stop_count": 12},
    ]
    assert classify_csv_format(
        [line.split(",") for line in FORMAT_C_CSV.strip().split("\n")]
    ) == "C"


def test_format_c_blank_or_invalid_number_defaults_to_one():
    csv_text = (
        "WC1X 0GB,\n"          # blank
        "SE1 9JE,not-a-number\n"  # invalid
        "PL4 6AB,5\n"           # valid, kept as-is
    )

    rows = parse_csv_rows_normalised(csv_text)

    assert rows == [
        {"address": "WC1X 0GB", "stop_count": 1},
        {"address": "SE1 9JE", "stop_count": 1},
        {"address": "PL4 6AB", "stop_count": 5},
    ]


def test_format_c_not_confused_with_recognised_legacy_header_words():
    """A first row that IS a recognised legacy header word (e.g. 'Notes')
    must not be swept into Format C just because the data rows below it
    happen to have two columns - it should still fall back to legacy."""
    rows = parse_csv_rows_normalised(UNSUPPORTED_HEADERS_CSV)

    assert rows == []


def test_headerless_rows_with_inconsistent_column_counts_fall_back_to_legacy():
    """If rows don't consistently have exactly two columns, this isn't the
    Format C shape - it should fall through to the legacy parser rather
    than being force-fit into address/stop_count columns."""
    csv_text = "WC1X 0GB\nEC3M 1EB,20\n"

    csv_format = classify_csv_format([row.split(",") for row in csv_text.strip().split("\n")])

    assert csv_format is None


def test_upload_csv_endpoint_accepts_headerless_compatibility_format(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "csv-format-c.db")
    database.init_db(force=True)

    async def fake_optimise_route(**_kwargs):
        return {
            "optimised_order": [0, 1, 2],
            "ordered_addresses": ["WC1X 0GB", "EC3M 1EB", "EC2A 2EG"],
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
            "stops_count": 3,
            "geocoded_count": 3,
            "failed_addresses": [],
        }

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", FORMAT_C_CSV, "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["X-CSV-Format-Detected"] == "headerless_postcode_number"


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
    assert response.headers["X-CSV-Format-Detected"] == "property"


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
    assert response.headers["X-CSV-Format-Detected"] == "postcode_number"


def test_upload_csv_endpoint_reports_legacy_format_for_older_csv_shapes(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "csv-legacy-format.db")
    database.init_db(force=True)

    async def fake_optimise_route(**_kwargs):
        return {
            "optimised_order": [0, 1],
            "ordered_addresses": ["Plymouth PL1", "Exeter EX1"],
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
        files={"file": ("stops.csv", "Plymouth PL1\nExeter EX1\n", "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["X-CSV-Format-Detected"] == "legacy"


def test_upload_csv_endpoint_rejects_unsupported_headers_with_clear_message():
    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", UNSUPPORTED_HEADERS_CSV, "text/csv")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Could not find any valid delivery stops" in detail
    assert "Postcode,Number" in detail
    assert "WC1X 0GB,1" in detail
    assert "Property Name,Address,Postcode,Type" in detail


def test_upload_csv_endpoint_malformed_one_column_file_gives_clear_message():
    """A file with rows present but no usable content in any cell (not
    literally empty, so it's a distinct case from the empty-file check)
    must fail with the same specific 'nothing found' message as any other
    unreadable CSV, not a stack trace or a generic 500."""
    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", ",,\n,,\n", "text/csv")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Could not find any valid delivery stops" in detail
    assert "Postcode,Number" in detail


def test_upload_csv_endpoint_empty_file_gives_specific_message():
    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", "", "text/csv")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "appears to be empty" in detail


def test_upload_csv_endpoint_single_stop_gives_specific_message():
    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.csv", "Postcode,Number\nWC1X 0GB,1\n", "text/csv")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Only found 1 valid delivery stop" in detail


def test_upload_csv_endpoint_rejects_non_csv_file_with_filename():
    response = client.post(
        "/quantum/upload-csv",
        files={"file": ("stops.txt", "Plymouth PL1\nExeter EX1\n", "text/plain")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "stops.txt" in detail
    assert ".csv" in detail
