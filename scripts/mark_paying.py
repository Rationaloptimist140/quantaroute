"""Manually mark an identifier (usually a visitor IP address) as a paying
user, bypassing the 30-day free-trial check for that identifier going
forward.

This is an immediate stopgap for the "owner blocked by their own free trial"
issue. The durable fix is the ADMIN_KEY / ADMIN_BYPASS_IPS mechanism in
backend/main.py, which does not require running this script again after
every deploy or IP change. Use this script only when you need to unblock a
specific already-recorded identifier right now.

Usage (local/dev, SQLite):

    cd backend
    python ../scripts/mark_paying.py --identifier 203.0.113.5

Usage against production Postgres:

    $env:DATABASE_URL="postgresql://user:password@host:5432/database"
    python scripts/mark_paying.py --identifier 203.0.113.5
    $env:DATABASE_URL=$null

To find your own current identifier (public IP as QuantaRoute sees it),
visit https://quantaroute.co.uk/health while watching the Render logs, or
just check https://whatismyipaddress.com from the same network you use to
test.
"""

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import mark_identifier_as_paying, using_postgres  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mark an identifier (IP address) as a paying user."
    )
    parser.add_argument(
        "--identifier",
        required=True,
        help="The identifier to mark as paying, usually an IP address.",
    )
    args = parser.parse_args()

    user = mark_identifier_as_paying(args.identifier)

    storage = "Postgres DATABASE_URL" if using_postgres() else "local SQLite"
    print(f"Storage: {storage}")
    print(f"Identifier: {user['identifier']}")
    print(f"is_paying: {bool(user['is_paying'])}")
    print(f"route_count: {user['route_count']}")
    print(
        "This identifier will now bypass the 30-day free-trial check. "
        "Consider setting ADMIN_KEY/ADMIN_BYPASS_IPS instead so this "
        "doesn't need repeating."
    )


if __name__ == "__main__":
    main()
