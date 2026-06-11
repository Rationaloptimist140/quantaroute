"""Create a QuantaRoute API key for local/dev/admin use.

The raw key is printed once. Only its SHA-256 hash is stored.
"""

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import create_api_key, using_postgres  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a QuantaRoute API key.")
    parser.add_argument("--label", required=True, help="Human-readable client label.")
    parser.add_argument(
        "--monthly-limit",
        type=int,
        default=None,
        help="Optional future monthly request limit. Not enforced yet.",
    )
    parser.add_argument(
        "--source-label",
        default=None,
        help="Optional route-history source/client label.",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional admin notes stored with the key record.",
    )
    args = parser.parse_args()

    record = create_api_key(
        args.label,
        monthly_limit=args.monthly_limit,
        source_label=args.source_label,
        notes=args.notes,
    )

    storage = "Postgres DATABASE_URL" if using_postgres() else "local SQLite"
    print("QuantaRoute API key created.")
    print(f"Storage: {storage}")
    print(f"ID: {record['id']}")
    print(f"Label: {record['label']}")
    monthly_limit = record.get("monthly_limit")
    print(f"Monthly limit: {monthly_limit if monthly_limit is not None else 'unlimited'}")
    print("Raw key, shown once:")
    print(record["api_key"])


if __name__ == "__main__":
    main()
