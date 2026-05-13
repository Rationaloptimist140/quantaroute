"""SQLite route history storage for QuantaRoute."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "quantaroute.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    # Render free-tier filesystems are ephemeral; this still gives local/session history.
    with get_connection() as conn:
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


def save_route(driver_name: str, result: dict[str, Any]) -> int:
    init_db()
    ordered_addresses = json.dumps(result.get("ordered_addresses", []))
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO routes (
                driver_name,
                stops_count,
                fuel_saving_percent,
                total_distance_km,
                naive_distance_km,
                ordered_addresses,
                maps_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                driver_name,
                result.get("stops_count"),
                result.get("fuel_saving_percent"),
                result.get("total_distance_km"),
                result.get("naive_distance_km"),
                ordered_addresses,
                result.get("maps_url"),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_recent_routes(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                driver_name,
                stops_count,
                fuel_saving_percent,
                total_distance_km,
                ordered_addresses,
                maps_url,
                created_at
            FROM routes
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    history = []
    for row in rows:
        record = dict(row)
        try:
            record["ordered_addresses"] = json.loads(record["ordered_addresses"] or "[]")
        except json.JSONDecodeError:
            record["ordered_addresses"] = []
        history.append(record)
    return history


def get_or_create_user(identifier: str) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
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


def parse_sqlite_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace(" ", "T"))


def is_within_free_month(first_used: str) -> bool:
    trial_start_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    return parse_sqlite_timestamp(first_used) >= trial_start_cutoff


def record_allowed_route_use(identifier: str) -> tuple[bool, dict[str, Any]]:
    user = get_or_create_user(identifier)
    if not is_within_free_month(user["first_used"]) and not int(user["is_paying"]):
        return False, user

    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET route_count = route_count + 1 WHERE identifier = ?",
            (identifier,),
        )
        conn.commit()

    user = get_or_create_user(identifier)
    return True, user
