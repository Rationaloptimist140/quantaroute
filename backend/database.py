"""Route history and usage storage for QuantaRoute.

Use Postgres when DATABASE_URL is configured, otherwise fall back to the local
SQLite file. This keeps local development dependency-light while letting
production route sheets survive Render restarts and redeploys.
"""

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - only needed when DATABASE_URL is set.
    psycopg = None
    dict_row = None


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "quantaroute.db"
_SCHEMA_READY_FOR: str | None = None


ROUTE_SELECT_COLUMNS = """
    id,
    driver_name,
    stops_count,
    fuel_saving_percent,
    total_distance_km,
    naive_distance_km,
    original_order_distance_km,
    nearest_neighbour_distance_km,
    final_selected_distance_km,
    fuel_saving_percent_vs_original,
    start_address,
    end_address,
    return_to_start,
    original_addresses,
    ordered_addresses,
    ordered_stops,
    original_distance_km,
    optimised_distance_km,
    distance_saved_km,
    estimated_saving_percent,
    maps_url,
    google_maps_url,
    whatsapp_url,
    whatsapp_message,
    warnings,
    source,
    vehicle,
    optimise_for,
    created_at
"""


SQLITE_ROUTE_COLUMNS = [
    ("original_order_distance_km", "REAL"),
    ("nearest_neighbour_distance_km", "REAL"),
    ("final_selected_distance_km", "REAL"),
    ("fuel_saving_percent_vs_original", "REAL"),
    ("start_address", "TEXT"),
    ("end_address", "TEXT"),
    ("return_to_start", "INTEGER DEFAULT 0"),
    ("original_addresses", "TEXT"),
    ("ordered_stops", "TEXT"),
    ("original_distance_km", "REAL"),
    ("optimised_distance_km", "REAL"),
    ("distance_saved_km", "REAL"),
    ("estimated_saving_percent", "REAL"),
    ("google_maps_url", "TEXT"),
    ("whatsapp_url", "TEXT"),
    ("whatsapp_message", "TEXT"),
    ("warnings", "TEXT"),
    ("source", "TEXT"),
    ("vehicle", "TEXT"),
    ("optimise_for", "TEXT"),
]


POSTGRES_ROUTE_COLUMNS = [
    ("original_order_distance_km", "DOUBLE PRECISION"),
    ("nearest_neighbour_distance_km", "DOUBLE PRECISION"),
    ("final_selected_distance_km", "DOUBLE PRECISION"),
    ("fuel_saving_percent_vs_original", "DOUBLE PRECISION"),
    ("start_address", "TEXT"),
    ("end_address", "TEXT"),
    ("return_to_start", "BOOLEAN DEFAULT FALSE"),
    ("original_addresses", "TEXT"),
    ("ordered_stops", "TEXT"),
    ("original_distance_km", "DOUBLE PRECISION"),
    ("optimised_distance_km", "DOUBLE PRECISION"),
    ("distance_saved_km", "DOUBLE PRECISION"),
    ("estimated_saving_percent", "DOUBLE PRECISION"),
    ("google_maps_url", "TEXT"),
    ("whatsapp_url", "TEXT"),
    ("whatsapp_message", "TEXT"),
    ("warnings", "TEXT"),
    ("source", "TEXT"),
    ("vehicle", "TEXT"),
    ("optimise_for", "TEXT"),
]


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def using_postgres() -> bool:
    return bool(get_database_url())


def storage_key() -> str:
    if using_postgres():
        return f"postgres:{normalise_database_url(get_database_url())}"
    return f"sqlite:{DB_PATH}"


def normalise_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return "postgresql://" + database_url.removeprefix("postgres://")
    return database_url


def get_sqlite_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres_connection() -> Any:
    if psycopg is None or dict_row is None:
        raise RuntimeError(
            "DATABASE_URL is set but psycopg is not installed. "
            "Install requirements.txt before using Postgres storage."
        )
    return psycopg.connect(normalise_database_url(get_database_url()), row_factory=dict_row)


def get_connection() -> Any:
    if using_postgres():
        return get_postgres_connection()
    return get_sqlite_connection()


def ensure_sqlite_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def ensure_postgres_column(
    conn: Any,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    ).fetchone()
    if row is None:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def init_sqlite() -> None:
    # Local fallback only. Render free-tier filesystems are ephemeral, so use
    # DATABASE_URL/Postgres in production when route-sheet persistence matters.
    with get_sqlite_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_name TEXT,
                stops_count INTEGER,
                fuel_saving_percent REAL,
                total_distance_km REAL,
                naive_distance_km REAL,
                ordered_addresses TEXT,
                maps_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for column_name, column_definition in SQLITE_ROUTE_COLUMNS:
            ensure_sqlite_column(conn, "routes", column_name, column_definition)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identifier TEXT UNIQUE,
                first_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                route_count INTEGER DEFAULT 0,
                is_paying INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()


def init_postgres() -> None:
    with get_postgres_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS routes (
                id BIGSERIAL PRIMARY KEY,
                driver_name TEXT,
                stops_count INTEGER,
                fuel_saving_percent DOUBLE PRECISION,
                total_distance_km DOUBLE PRECISION,
                naive_distance_km DOUBLE PRECISION,
                ordered_addresses TEXT,
                maps_url TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for column_name, column_definition in POSTGRES_ROUTE_COLUMNS:
            ensure_postgres_column(conn, "routes", column_name, column_definition)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                identifier TEXT UNIQUE,
                first_used TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                route_count INTEGER DEFAULT 0,
                is_paying INTEGER DEFAULT 0
            )
            """
        )


def init_db(force: bool = False) -> None:
    global _SCHEMA_READY_FOR
    key = storage_key()
    if not force and _SCHEMA_READY_FOR == key:
        return

    if using_postgres():
        init_postgres()
    else:
        init_sqlite()
    _SCHEMA_READY_FOR = key


def json_list(value: Any) -> str:
    if value is None:
        value = []
    if isinstance(value, str):
        value = [value]
    return json.dumps(list(value))


def first_float(*values: Any) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def build_route_record(
    driver_name: str,
    result: dict[str, Any],
    *,
    source: str = "web",
    vehicle: str | None = None,
    optimise_for: str | None = None,
    original_addresses: list[str] | None = None,
    warnings: list[str] | None = None,
    whatsapp_message: str | None = None,
) -> dict[str, Any]:
    ordered_stops = result.get("ordered_stops") or result.get("ordered_addresses") or []
    original_stops = original_addresses if original_addresses is not None else result.get("original_addresses", [])
    original_distance = first_float(
        result.get("original_distance_km"),
        result.get("original_order_distance_km"),
        result.get("naive_distance_km"),
    )
    optimised_distance = first_float(
        result.get("optimised_distance_km"),
        result.get("final_selected_distance_km"),
        result.get("total_distance_km"),
    )
    distance_saved = round(max(original_distance - optimised_distance, 0.0), 2)
    estimated_saving_percent = first_float(
        result.get("estimated_saving_percent"),
        result.get("fuel_saving_percent_vs_original"),
        result.get("fuel_saving_percent"),
    )
    maps_url = result.get("google_maps_url") or result.get("maps_url") or ""

    return {
        "driver_name": driver_name,
        "stops_count": result.get("stops_count") or len(ordered_stops),
        "fuel_saving_percent": result.get("fuel_saving_percent"),
        "total_distance_km": result.get("total_distance_km"),
        "naive_distance_km": result.get("naive_distance_km"),
        "original_order_distance_km": result.get("original_order_distance_km"),
        "nearest_neighbour_distance_km": result.get("nearest_neighbour_distance_km"),
        "final_selected_distance_km": result.get("final_selected_distance_km"),
        "fuel_saving_percent_vs_original": result.get("fuel_saving_percent_vs_original"),
        "start_address": result.get("start_address"),
        "end_address": result.get("end_address"),
        "return_to_start": bool(result.get("return_to_start")),
        "original_addresses": json_list(original_stops),
        "ordered_addresses": json_list(ordered_stops),
        "ordered_stops": json_list(ordered_stops),
        "original_distance_km": original_distance,
        "optimised_distance_km": optimised_distance,
        "distance_saved_km": distance_saved,
        "estimated_saving_percent": estimated_saving_percent,
        "maps_url": maps_url,
        "google_maps_url": maps_url,
        "whatsapp_url": result.get("whatsapp_url"),
        "whatsapp_message": whatsapp_message or result.get("whatsapp_message"),
        "warnings": json_list(warnings if warnings is not None else result.get("warnings", [])),
        "source": source,
        "vehicle": vehicle,
        "optimise_for": optimise_for,
    }


def save_route(
    driver_name: str,
    result: dict[str, Any],
    *,
    source: str = "web",
    vehicle: str | None = None,
    optimise_for: str | None = None,
    original_addresses: list[str] | None = None,
    warnings: list[str] | None = None,
    whatsapp_message: str | None = None,
) -> int:
    init_db()
    record = build_route_record(
        driver_name,
        result,
        source=source,
        vehicle=vehicle,
        optimise_for=optimise_for,
        original_addresses=original_addresses,
        warnings=warnings,
        whatsapp_message=whatsapp_message,
    )

    columns = list(record)
    values = [record[column] for column in columns]

    if using_postgres():
        placeholders = ", ".join(["%s"] * len(columns))
        with get_postgres_connection() as conn:
            row = conn.execute(
                f"""
                INSERT INTO routes ({", ".join(columns)})
                VALUES ({placeholders})
                RETURNING id
                """,
                values,
            ).fetchone()
        return int(row["id"])

    placeholders = ", ".join(["?"] * len(columns))
    with get_sqlite_connection() as conn:
        cursor = conn.execute(
            f"""
            INSERT INTO routes ({", ".join(columns)})
            VALUES ({placeholders})
            """,
            values,
        )
        conn.commit()
        return int(cursor.lastrowid)


def parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return str(value).strip().lower() in {"1", "t", "true", "yes", "y"}


def decode_route_row(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    record = dict(row)
    ordered_addresses = parse_json_list(
        record.get("ordered_addresses") or record.get("ordered_stops")
    )
    ordered_stops = parse_json_list(record.get("ordered_stops") or record.get("ordered_addresses"))
    original_addresses = parse_json_list(record.get("original_addresses"))

    record["ordered_addresses"] = ordered_addresses
    record["ordered_stops"] = ordered_stops or ordered_addresses
    record["original_addresses"] = original_addresses
    record["warnings"] = parse_json_list(record.get("warnings"))
    record["return_to_start"] = parse_bool(record.get("return_to_start"))

    record["maps_url"] = record.get("maps_url") or record.get("google_maps_url") or ""
    record["google_maps_url"] = record.get("google_maps_url") or record.get("maps_url") or ""
    record["original_order_distance_km"] = first_float(
        record.get("original_order_distance_km"),
        record.get("original_distance_km"),
        record.get("naive_distance_km"),
    )
    record["naive_distance_km"] = first_float(
        record.get("naive_distance_km"),
        record.get("original_distance_km"),
        record.get("original_order_distance_km"),
    )
    record["final_selected_distance_km"] = first_float(
        record.get("final_selected_distance_km"),
        record.get("optimised_distance_km"),
        record.get("total_distance_km"),
    )
    record["total_distance_km"] = first_float(
        record.get("total_distance_km"),
        record.get("optimised_distance_km"),
        record.get("final_selected_distance_km"),
    )
    record["fuel_saving_percent_vs_original"] = first_float(
        record.get("fuel_saving_percent_vs_original"),
        record.get("estimated_saving_percent"),
        record.get("fuel_saving_percent"),
    )
    record["fuel_saving_percent"] = first_float(
        record.get("fuel_saving_percent"),
        record.get("estimated_saving_percent"),
        record.get("fuel_saving_percent_vs_original"),
    )
    return record


def get_recent_routes(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    if using_postgres():
        with get_postgres_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {ROUTE_SELECT_COLUMNS}
                FROM routes
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
    else:
        with get_sqlite_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {ROUTE_SELECT_COLUMNS}
                FROM routes
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    return [record for row in rows if (record := decode_route_row(row)) is not None]


def get_route_by_id(route_id: int) -> dict[str, Any] | None:
    init_db()
    if using_postgres():
        with get_postgres_connection() as conn:
            row = conn.execute(
                f"""
                SELECT {ROUTE_SELECT_COLUMNS}
                FROM routes
                WHERE id = %s
                """,
                (route_id,),
            ).fetchone()
    else:
        with get_sqlite_connection() as conn:
            row = conn.execute(
                f"""
                SELECT {ROUTE_SELECT_COLUMNS}
                FROM routes
                WHERE id = ?
                """,
                (route_id,),
            ).fetchone()
    return decode_route_row(row)


def get_or_create_user(identifier: str) -> dict[str, Any]:
    init_db()
    if using_postgres():
        with get_postgres_connection() as conn:
            conn.execute(
                "INSERT INTO users (identifier) VALUES (%s) ON CONFLICT (identifier) DO NOTHING",
                (identifier,),
            )
            row = conn.execute(
                """
                SELECT id, identifier, first_used, route_count, is_paying
                FROM users
                WHERE identifier = %s
                """,
                (identifier,),
            ).fetchone()
    else:
        with get_sqlite_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (identifier) VALUES (?)",
                (identifier,),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT id, identifier, first_used, route_count, is_paying
                FROM users
                WHERE identifier = ?
                """,
                (identifier,),
            ).fetchone()

    if row is None:
        raise RuntimeError("Could not create or load usage record")
    return dict(row)


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    else:
        text = str(value).replace("Z", "+00:00").replace(" ", "T")
        timestamp = datetime.fromisoformat(text)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def is_within_free_month(first_used: Any) -> bool:
    trial_start_cutoff = datetime.now(UTC) - timedelta(days=30)
    return parse_timestamp(first_used) >= trial_start_cutoff


def record_allowed_route_use(identifier: str) -> tuple[bool, dict[str, Any]]:
    user = get_or_create_user(identifier)
    if not is_within_free_month(user["first_used"]) and not int(user["is_paying"]):
        return False, user

    if using_postgres():
        with get_postgres_connection() as conn:
            conn.execute(
                "UPDATE users SET route_count = route_count + 1 WHERE identifier = %s",
                (identifier,),
            )
    else:
        with get_sqlite_connection() as conn:
            conn.execute(
                "UPDATE users SET route_count = route_count + 1 WHERE identifier = ?",
                (identifier,),
            )
            conn.commit()

    user = get_or_create_user(identifier)
    return True, user
