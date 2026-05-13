"""SQLite route history storage for QuantaRoute."""

import json
import sqlite3
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
