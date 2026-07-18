"""
QuantaRoute — FastAPI Main Entry Point
"""

import sys
import os
import csv
import io
import re
import secrets as secrets_lib
import hashlib
from pathlib import Path
from typing import Literal

try:
    import stripe
except ImportError:  # pragma: no cover - only needed once STRIPE_SECRET_KEY is set.
    stripe = None

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services'))

from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import logging

from services.route_builder import (
    GEOCODING_HELP_MESSAGE,
    RouteGeocodingError,
    build_google_maps_url,
    build_whatsapp_message,
    clean_route_address,
    optimise_route,
)
from services.route_sheet import build_route_sheet_html

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONTACT_EMAIL = "hi@quantaroute.co.uk"
SUPPORT_EMAIL = "hi@quantaroute.co.uk"
APP_BUILD = "admin-bypass-subscription-2026-07-17"

app = FastAPI(
    title="QuantaRoute API",
    description="Road-network delivery route optimisation for UK couriers",
    version="1.0.0",
    contact={
        "name": "QuantaRoute",
        "email": CONTACT_EMAIL,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
ASSETS_DIR = FRONTEND_DIR / "assets"

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

from database import (
    api_keys_available,
    create_api_key,
    get_api_key_by_stripe_customer_id,
    get_api_key_by_stripe_subscription,
    get_database_url,
    get_recent_routes,
    get_route_by_id,
    init_db,
    record_allowed_route_use,
    record_usage_event,
    save_route,
    set_api_key_active,
    usage_tracking_available,
    using_postgres,
    validate_and_record_api_key,
)

try:
    init_db()
except Exception:
    logger.exception(
        "Database initialisation failed during startup; continuing so /health can report diagnostics."
    )
UPGRADE_URL = "https://quantaroute.onrender.com/pricing"
MAX_PUBLIC_ADDRESS_LENGTH = 240

# --- Admin / owner bypass -----------------------------------------------
#
# The free-trial gate below (enforce_usage_limit) blocks any identifier (IP
# address) 30 days after its first use, with no built-in exception for the
# site owner. That meant the owner's own IP got permanently 402'd once their
# original test traffic aged past 30 days. This section adds a durable,
# env-configured bypass so that doesn't happen again:
#
#   ADMIN_KEY           - a shared secret. Visiting ANY URL once with
#                          ?admin_key=<ADMIN_KEY> sets a long-lived signed
#                          cookie that bypasses the trial/paywall gate on all
#                          later requests from that browser. The same value
#                          can also be sent as an X-Admin-Key header (useful
#                          for scripts/Postman/curl instead of a browser).
#   ADMIN_BYPASS_IPS     - optional comma-separated list of IP addresses that
#                          always bypass the gate, no key needed. Useful as a
#                          belt-and-braces fallback for a known static office
#                          IP, but IPs change, so ADMIN_KEY is the primary
#                          mechanism.
#
# Neither of these affects paying customers or the free-trial logic for
# normal visitors; they only add an override path for the owner.
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()
ADMIN_COOKIE_NAME = "qr_admin"
ADMIN_BYPASS_IPS = {
    ip.strip()
    for ip in os.getenv("ADMIN_BYPASS_IPS", "").split(",")
    if ip.strip()
}


def _admin_cookie_value() -> str:
    if not ADMIN_KEY:
        return ""
    return hashlib.sha256(f"quantaroute-admin:{ADMIN_KEY}".encode("utf-8")).hexdigest()


ADMIN_COOKIE_VALUE = _admin_cookie_value()


def is_admin_request(request: Request) -> bool:
    if not ADMIN_KEY and not ADMIN_BYPASS_IPS:
        return False

    if ADMIN_KEY:
        header_key = request.headers.get("x-admin-key", "")
        if header_key and secrets_lib.compare_digest(header_key, ADMIN_KEY):
            return True

        query_key = request.query_params.get("admin_key", "")
        if query_key and secrets_lib.compare_digest(query_key, ADMIN_KEY):
            return True

        cookie_value = request.cookies.get(ADMIN_COOKIE_NAME, "")
        if cookie_value and secrets_lib.compare_digest(cookie_value, ADMIN_COOKIE_VALUE):
            return True

    if ADMIN_BYPASS_IPS and get_client_identifier(request) in ADMIN_BYPASS_IPS:
        return True

    return False


@app.middleware("http")
async def admin_bypass_cookie_middleware(request: Request, call_next):
    """If a valid admin_key query param is present, set a long-lived cookie
    so the browser keeps bypassing the trial/paywall gate on later requests
    without needing the query param every time."""
    response = await call_next(request)
    if ADMIN_KEY:
        query_key = request.query_params.get("admin_key", "")
        if query_key and secrets_lib.compare_digest(query_key, ADMIN_KEY):
            response.set_cookie(
                ADMIN_COOKIE_NAME,
                ADMIN_COOKIE_VALUE,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="lax",
            )
    return response

# TODO: Add future per-identifier/IP/API-key rate limiting before wider launch.
# TODO: Add future unauthenticated public traffic throttling before wider launch.

# --- Stripe monthly plan (£1.99/month for up to 100 routes) -------------
#
# The monthly plan is modelled as an API key with monthly_limit=100 whose
# is_active flag tracks the linked Stripe subscription (see
# backend/database.py for the plan/stripe_customer_id/stripe_subscription_id
# columns). Flow:
#
#   1. GET /subscribe/monthly creates a Stripe Checkout Session for the
#      recurring price and redirects the browser to Stripe's hosted page.
#   2. On success, Stripe redirects back to /subscribe/success?session_id=...
#      which looks the API key up by the Checkout Session's customer id and
#      shows the raw key once (Stripe's session_id is the proof of purchase).
#   3. The webhook at POST /api/stripe/webhook is the source of truth: it
#      creates the API key on checkout.session.completed, and flips
#      is_active on customer.subscription.updated/deleted so a cancelled or
#      failed-payment subscription stops granting free routes.
#
# All three env vars below must be set before this does anything; if they
# are missing the subscribe endpoints return a clear 503 instead of crashing,
# and the rest of the site (free trial, pay-per-route, admin bypass) is
# unaffected either way.
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PRICE_ID_MONTHLY = os.getenv("STRIPE_PRICE_ID_MONTHLY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
MONTHLY_PLAN_ROUTE_LIMIT = 100

if stripe is not None and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def stripe_checkout_configured() -> bool:
    return bool(stripe is not None and STRIPE_SECRET_KEY and STRIPE_PRICE_ID_MONTHLY)


def stripe_not_configured_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "The monthly plan isn't set up yet. Email hi@quantaroute.co.uk "
                "to get started, or check back shortly."
            ),
        },
    )


@app.exception_handler(RequestValidationError)
async def api_validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "The request body is missing required fields or contains invalid values.",
                    "details": exc.errors(),
                },
            },
        )
    return await request_validation_exception_handler(request, exc)


def build_route_sheet_url(request: Request, route_id: int) -> str:
    return f"{str(request.base_url).rstrip('/')}/route-sheet/{route_id}"


def history_number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_recent_route_item(route: dict, request: Request) -> dict:
    route_id = route.get("id")
    return {
        "id": route_id,
        "created_at": str(route.get("created_at") or ""),
        "start_address": route.get("start_address") or "",
        "end_address": route.get("end_address") or "",
        "original_distance_km": history_number(route.get("original_distance_km") or route.get("original_order_distance_km")),
        "optimised_distance_km": history_number(route.get("optimised_distance_km") or route.get("final_selected_distance_km")),
        "distance_saved_km": history_number(route.get("distance_saved_km")),
        "estimated_saving_percent": history_number(route.get("estimated_saving_percent") or route.get("fuel_saving_percent_vs_original")),
        "route_sheet_url": build_route_sheet_url(request, int(route_id)) if route_id is not None else None,
    }


def record_route_history(
    driver_name: str,
    result: dict,
    *,
    source: str = "web",
    vehicle: str | None = "van",
    optimise_for: str | None = "distance",
    original_addresses: list[str] | None = None,
    warnings: list[str] | None = None,
    whatsapp_message: str | None = None,
) -> int | None:
    try:
        return save_route(
            driver_name=driver_name,
            result=result,
            source=source,
            vehicle=vehicle,
            optimise_for=optimise_for,
            original_addresses=original_addresses,
            warnings=warnings,
            whatsapp_message=whatsapp_message,
        )
    except Exception as e:
        logger.error(f"Failed to save route history: {e}")
        return None


def get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_usage_limit(request: Request) -> JSONResponse | None:
    if is_admin_request(request):
        logger.info("Admin bypass granted for %s", get_client_identifier(request))
        return None

    identifier = get_client_identifier(request)
    allowed, user = record_allowed_route_use(identifier)
    if allowed:
        logger.info(
            "Usage allowed for %s; route_count=%s",
            identifier,
            user.get("route_count"),
        )
        return None

    return JSONResponse(
        status_code=402,
        content={
            "detail": "Free trial ended. Please upgrade to continue at £1.99 per route, or subscribe to the monthly plan.",
            "upgrade_url": UPGRADE_URL,
        },
    )

def is_csv_header_row(cells: list[str]) -> bool:
    headers = {
        "stop",
        "stop number",
        "business",
        "business name",
        "company",
        "customer",
        "name",
        "address",
        "addresses",
        "postcode",
        "post code",
        "order",
        "order details",
        "notes",
    }
    return any(cell.strip().lower() in headers for cell in cells)


def is_postcode_only(value: str) -> bool:
    compact = value.strip().upper()
    return bool(
        re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", compact)
        or re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?", compact)
    )


def is_ignored_csv_cell(value: str) -> bool:
    text = value.strip()
    if not text or text.isdigit() or is_postcode_only(text):
        return True
    return text.lower() in {
        "stop",
        "stop number",
        "address",
        "addresses",
        "postcode",
        "post code",
        "order",
        "order details",
        "notes",
        "qty",
        "quantity",
        "item",
        "items",
    }


def looks_address_like_cell(value: str) -> bool:
    return bool(
        re.search(
            r"\d|,|\b(road|rd|street|st|lane|ln|avenue|ave|drive|dr|way|close|cl|place|pl|plymouth|exeter|bristol)\b",
            value,
            flags=re.IGNORECASE,
        )
    )


def get_csv_header_map(rows: list[list[str]]) -> dict[str, int | bool]:
    first_row = [clean_route_address(cell).lower() for cell in (rows[0] if rows else [])]
    if not is_csv_header_row(first_row):
        return {"has_header": False, "business_index": -1, "address_index": -1}

    business_index = next(
        (
            index
            for index, header in enumerate(first_row)
            if re.search(r"business|company|customer|client|venue|name", header)
            and not re.search(r"address|order", header)
        ),
        -1,
    )
    address_index = next(
        (
            index
            for index, header in enumerate(first_row)
            if re.search(r"address|addr|street|line 1|line1", header)
            and "email" not in header
        ),
        -1,
    )
    return {
        "has_header": True,
        "business_index": business_index,
        "address_index": address_index,
    }


def combine_business_and_address(business_name: str, address_text: str) -> str:
    business = clean_route_address(business_name)
    address = clean_route_address(address_text)
    if not address:
        return ""
    if not business or is_ignored_csv_cell(business):
        return address
    if address.lower().startswith(business.lower()):
        return address
    return f"{business}, {address}"


def first_address_like_cell(cells: list[str]) -> str:
    for cell in cells:
        if is_ignored_csv_cell(cell):
            continue
        if looks_address_like_cell(cell):
            return cell
    return ""


def extract_csv_address(
    row: list[str],
    header_map: dict[str, int | bool],
    row_index: int,
) -> str:
    cells = [clean_route_address(cell) for cell in row]
    if not any(cells) or (row_index == 0 and header_map["has_header"]):
        return ""

    if len(cells) == 1:
        return cells[0]

    address_index = int(header_map["address_index"])
    business_index = int(header_map["business_index"])
    if address_index >= 0:
        business = cells[business_index] if business_index >= 0 else ""
        address = cells[address_index] if address_index < len(cells) else ""
        return combine_business_and_address(business, address)

    if (
        len(cells) >= 3
        and not is_ignored_csv_cell(cells[2])
        and (is_ignored_csv_cell(cells[0]) or looks_address_like_cell(cells[2]))
    ):
        return combine_business_and_address(cells[1], cells[2])

    if (
        len(cells) >= 2
        and not is_ignored_csv_cell(cells[1])
        and (is_ignored_csv_cell(cells[0]) or looks_address_like_cell(cells[1]))
    ):
        business = "" if is_ignored_csv_cell(cells[0]) else cells[0]
        return combine_business_and_address(business, cells[1])

    return clean_route_address(
        first_address_like_cell(cells)
        or next((cell for cell in cells if not is_ignored_csv_cell(cell)), "")
    )


def parse_csv_addresses(decoded_csv: str) -> list[str]:
    rows = list(csv.reader(io.StringIO(decoded_csv)))
    header_map = get_csv_header_map(rows)
    return [
        address
        for index, row in enumerate(rows)
        if (address := extract_csv_address(row, header_map, index))
    ]

class RouteRequest(BaseModel):
    addresses: list[str]
    driver_name: str = "Driver"
    start_address: str | None = None
    return_to_start: bool = False

class RouteResponse(BaseModel):
    optimised_order: list[int]
    ordered_addresses: list[str]
    start_address: str | None = None
    return_to_start: bool = False
    total_distance_km: float
    naive_distance_km: float
    fuel_saving_percent: float
    original_order_distance_km: float
    nearest_neighbour_distance_km: float
    final_selected_distance_km: float
    fuel_saving_percent_vs_original: float
    maps_url: str
    whatsapp_url: str
    route_sheet_url: str | None = None
    algorithm_used: str | None = None
    stops_count: int
    geocoded_count: int
    failed_addresses: list[str]


class PublicOptimiseRouteRequest(BaseModel):
    start: str = Field(
        ...,
        min_length=1,
        examples=["Plymouth, UK"],
        description="Starting location, depot, home base, or first pickup point.",
    )
    stops: list[str] = Field(
        ...,
        min_length=2,
        json_schema_extra={"maxItems": 20},
        examples=[[
            "Drake Circus Shopping Centre, Plymouth",
            "Royal William Yard, Plymouth",
            "Plymouth Market, Plymouth",
            "Plymouth Railway Station, Plymouth",
        ]],
        description="Delivery or appointment stops to reorder. Initially supports 2 to 20 stops.",
    )
    end: str | None = Field(
        default=None,
        examples=["Plymouth, UK"],
        description="Optional final destination. If omitted, the route ends at the final optimised stop.",
    )
    vehicle: str = Field(default="van", examples=["van"])
    optimise_for: Literal["distance", "time"] = Field(default="distance")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "start": "Plymouth, UK",
                    "stops": [
                        "Drake Circus Shopping Centre, Plymouth",
                        "Royal William Yard, Plymouth",
                        "Plymouth Market, Plymouth",
                        "Plymouth Railway Station, Plymouth",
                    ],
                    "end": "Plymouth, UK",
                    "vehicle": "van",
                    "optimise_for": "distance",
                }
            ]
        }
    }


class PublicRouteError(BaseModel):
    code: str
    message: str
    details: list[str] | list[dict] = Field(default_factory=list)


class ApiClientMetadata(BaseModel):
    label: str
    usage_count_current_month: int
    monthly_limit: int | None = None


class PublicOptimiseRouteSuccess(BaseModel):
    success: bool
    input_stop_count: int
    ordered_stops: list[str]
    original_distance_km: float
    optimised_distance_km: float
    distance_saved_km: float
    estimated_saving_percent: float
    algorithm_used: str | None = None
    google_maps_url: str
    whatsapp_message: str
    route_sheet_url: str | None = None
    api_client: ApiClientMetadata | None = None
    warnings: list[str]

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "input_stop_count": 4,
                "ordered_stops": [
                    "Plymouth, UK",
                    "Plymouth Railway Station, Plymouth",
                    "Plymouth Market, Plymouth",
                    "Drake Circus Shopping Centre, Plymouth",
                    "Royal William Yard, Plymouth",
                    "Plymouth, UK",
                ],
                "original_distance_km": 22.0,
                "optimised_distance_km": 19.1,
                "distance_saved_km": 2.9,
                "estimated_saving_percent": 13.2,
                "algorithm_used": "exact brute force",
                "google_maps_url": "https://www.google.com/maps/dir/Plymouth%2C%20UK/...",
                "whatsapp_message": "Hi Driver! Your optimised route is ready. Tap to open in Google Maps: https://www.google.com/maps/dir/...",
                "route_sheet_url": "https://quantaroute.co.uk/route-sheet/123",
                "api_client": {
                    "label": "Example Courier Tool",
                    "usage_count_current_month": 12,
                    "monthly_limit": 1000,
                },
                "warnings": [
                    "Distance estimates compare route candidates against the address order entered.",
                    "Drivers must follow live road conditions, vehicle restrictions, and professional judgement.",
                ],
            }
        }
    }


class PublicOptimiseRouteErrorResponse(BaseModel):
    success: bool = False
    error: PublicRouteError


def public_api_error(
    status_code: int,
    code: str,
    message: str,
    details: list[str] | list[dict] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
            },
        },
    )


def api_client_response_metadata(api_client: dict | None) -> dict:
    if not api_client:
        return {"api_client": None}
    return {
        "api_client": {
            "label": api_client.get("label"),
            "usage_count_current_month": int(api_client.get("usage_count_current_month") or 0),
            "monthly_limit": api_client.get("monthly_limit"),
        }
    }


def clean_public_stops(stops: list[str]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    clean_stops: list[str] = []
    seen: set[str] = set()

    for raw_stop in stops:
        stop = clean_route_address(raw_stop)
        if not stop:
            warnings.append("Empty stop removed.")
            continue

        key = stop.casefold()
        if key in seen:
            warnings.append(f"Duplicate stop removed: {stop}")
            continue

        seen.add(key)
        clean_stops.append(stop)

    return clean_stops, warnings


def too_long_addresses(addresses: list[str]) -> list[str]:
    return [
        address
        for address in addresses
        if len(clean_route_address(address)) > MAX_PUBLIC_ADDRESS_LENGTH
    ]


def public_route_warnings(
    request_data: PublicOptimiseRouteRequest,
    result: dict,
    input_warnings: list[str],
) -> list[str]:
    warnings = list(input_warnings)
    if request_data.optimise_for == "time":
        warnings.append("Time optimisation is not yet separate; distance optimisation was used.")
    if request_data.vehicle != "van":
        warnings.append("Vehicle type is accepted for API compatibility; current estimates use van-style routing.")
    if result.get("failed_addresses"):
        warnings.append(
            "Some stops could not be geocoded and were excluded: "
            + ", ".join(result["failed_addresses"])
        )
    warnings.append("Distance estimates compare route candidates against the address order entered.")
    warnings.append(
        "Estimated savings can vary due to traffic, road closures, driver behaviour, vehicle type, and delivery constraints."
    )
    return warnings


def build_public_ordered_stops(
    start: str,
    ordered_delivery_stops: list[str],
    end: str | None,
) -> list[str]:
    route = [clean_route_address(start)] + [
        clean_route_address(stop) for stop in ordered_delivery_stops if clean_route_address(stop)
    ]
    clean_end = clean_route_address(end or "")
    if clean_end:
        route.append(clean_end)
    return route


LLMS_TXT = """# QuantaRoute

QuantaRoute is a route optimisation tool for small UK couriers, multi-drop drivers, florists, mobile cleaners, tradespeople, property maintenance teams, estate agents, small retailers, and field service teams.

It turns delivery addresses into an optimised stop order, estimates distance and fuel savings, creates a Google Maps route link, and prepares a WhatsApp-ready driver message.

## Main API

POST /api/optimise-route

Use this endpoint when an AI assistant or business agent needs to optimise a route of 2-20 stops.

## Input summary

Required fields: start, stops.
Optional fields: end, vehicle, optimise_for.

Optional header during public testing: X-API-Key.

## Output summary

The API returns ordered stops, original distance, optimised distance, distance saved, estimated saving percent, Google Maps URL, WhatsApp driver message, route sheet URL, optional API client usage metadata, and warnings.

## API keys

API keys are optional while QuantaRoute is free to test. Send X-API-Key when a key is available. Invalid or inactive keys return 401, and keys over their monthly limit return 429. Paid/API access and higher limits will require API keys later. Raw API keys are not stored.

## Example task

“Here are 18 delivery addresses. Optimise the route, estimate distance and fuel saving, create a Google Maps link, and prepare a WhatsApp message for the driver.”

## Pricing

First month free for testing. Then £1.99 per optimised route, or a monthly plan at £1.99/month for up to 100 routes. Payments may still be in testing.

## Safety

QuantaRoute provides estimated route optimisation and fuel-saving calculations. It does not guarantee the mathematically shortest route in all cases. Drivers must follow road laws, live traffic conditions, vehicle restrictions, and professional judgement.

## Contact

hi@quantaroute.co.uk
"""

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "QuantaRoute API",
        "version": "1.0.0",
        "build": APP_BUILD,
        "storage_backend": "postgres" if using_postgres() else "sqlite",
        "database_configured": bool(get_database_url()),
    }


@app.get("/health/deep")
def health_deep():
    try:
        get_recent_routes(limit=1)
        route_history_available = True
    except Exception:
        route_history_available = False

    return {
        "status": "ok",
        "service": "QuantaRoute API",
        "version": "1.0.0",
        "build": APP_BUILD,
        "storage_backend": "postgres" if using_postgres() else "sqlite",
        "database_configured": bool(get_database_url()),
        "route_history_available": route_history_available,
        "api_keys_available": api_keys_available(),
        "usage_tracking_available": usage_tracking_available(),
        "admin_bypass_configured": bool(ADMIN_KEY or ADMIN_BYPASS_IPS),
        "stripe_package_installed": stripe is not None,
        "stripe_secret_key_set": bool(STRIPE_SECRET_KEY),
        "stripe_price_id_set": bool(STRIPE_PRICE_ID_MONTHLY),
        "stripe_webhook_secret_set": bool(STRIPE_WEBHOOK_SECRET),
        "stripe_checkout_configured": stripe_checkout_configured(),
    }


@app.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=False)
def llms_txt():
    return PlainTextResponse(LLMS_TXT, media_type="text/plain; charset=utf-8")

def frontend_file(filename: str) -> FileResponse:
    file_path = FRONTEND_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(
        file_path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def frontend():
    return frontend_file("index.html")

@app.get("/landing", include_in_schema=False)
@app.get("/landing.html", include_in_schema=False)
def landing_page():
    return frontend_file("landing.html")

@app.get("/developers", include_in_schema=False)
@app.get("/developers.html", include_in_schema=False)
def developers_page():
    return frontend_file("developers.html")

@app.get("/pricing", include_in_schema=False)
def pricing_page():
    return frontend_file("pricing.html")


@app.get("/subscribe/monthly", include_in_schema=False)
def subscribe_monthly(request: Request):
    """Start Stripe Checkout for the £1.99/month, up to 100 routes plan."""
    if not stripe_checkout_configured():
        return stripe_not_configured_response()

    base_url = str(request.base_url).rstrip("/")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID_MONTHLY, "quantity": 1}],
            success_url=f"{base_url}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/pricing",
            billing_address_collection="auto",
        )
    except Exception as e:  # noqa: BLE001 - surface a clean message either way
        logger.error(f"Stripe checkout session creation failed: {e}")
        # TODO: remove stripe_error from the response once checkout is
        # confirmed working end-to-end - it's temporarily included so the
        # failure is visible without digging through Render's Logs UI.
        # Stripe's own error strings mask secret values (e.g. "Invalid API
        # Key provided: 74916da2****...5260"), so this is safe to surface.
        return JSONResponse(
            status_code=502,
            content={
                "detail": "Could not start checkout. Please try again shortly.",
                "stripe_error": str(e),
            },
        )

    return RedirectResponse(session.url, status_code=303)


@app.get("/subscribe/success", response_class=HTMLResponse, include_in_schema=False)
def subscribe_success(session_id: str = ""):
    """Show the provisioned API key once, looked up via the Checkout Session
    id Stripe redirected back with. The webhook (not this page) is the
    source of truth for actually creating/activating the key - this page
    just displays it if the webhook has already run."""
    if not stripe_checkout_configured() or not session_id:
        return HTMLResponse(
            "<p>Missing or invalid checkout session. If you were charged, "
            "email hi@quantaroute.co.uk and we'll sort out your API key.</p>",
            status_code=400,
        )

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Could not retrieve Stripe checkout session {session_id}: {e}")
        return HTMLResponse(
            "<p>Could not verify your checkout session. Email "
            "hi@quantaroute.co.uk with your receipt and we'll sort out your "
            "API key.</p>",
            status_code=502,
        )

    customer_id = session.get("customer") if isinstance(session, dict) else getattr(session, "customer", None)
    record = get_api_key_by_stripe_customer_id(customer_id) if customer_id else None

    if record is None:
        # The webhook usually beats the browser redirect, but if it hasn't
        # landed yet, tell the customer their key is on the way rather than
        # showing an error.
        return HTMLResponse(
            "<p>Thanks! Your subscription is being set up. Refresh this page "
            "in a few seconds, or email hi@quantaroute.co.uk if your API key "
            "doesn't appear shortly.</p>"
        )

    # Raw API keys are never stored in our database (only a SHA-256 hash) -
    # the webhook stashes the raw key in Stripe Customer metadata for this
    # one-time pickup, and we clear it immediately after showing it so it
    # isn't sitting anywhere retrievable a second time.
    raw_key = None
    try:
        customer = stripe.Customer.retrieve(customer_id)
        raw_key = (customer.get("metadata") or {}).get("quantaroute_api_key")
        if raw_key:
            stripe.Customer.modify(customer_id, metadata={"quantaroute_api_key": ""})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Could not read/clear API key metadata for customer {customer_id}: {e}")

    if not raw_key:
        return HTMLResponse(
            "<h1>You're subscribed</h1>"
            "<p>Up to 100 optimised routes per month. Your API key has "
            "already been issued - if you didn't save it, email "
            "hi@quantaroute.co.uk with your receipt and we'll reissue one.</p>"
        )

    return HTMLResponse(
        "<h1>You're subscribed</h1>"
        "<p>Up to 100 optimised routes per month. Save this API key now - it "
        "will not be shown again:</p>"
        f"<pre style='padding:16px;background:#f0fdf4;border-radius:8px;font-size:16px;'>{raw_key}</pre>"
        "<p>Send it as the <code>X-API-Key</code> header on "
        "<code>POST /api/optimise-route</code>. Questions: hi@quantaroute.co.uk</p>"
    )


@app.post("/api/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    if stripe is None or not STRIPE_WEBHOOK_SECRET:
        # Not configured yet; acknowledge so Stripe doesn't retry forever,
        # but do nothing.
        return JSONResponse(status_code=200, content={"received": False})

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:  # noqa: BLE001 - invalid signature or payload
        logger.warning(f"Stripe webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        customer_id = data_object.get("customer")
        subscription_id = data_object.get("subscription")
        customer_email = (data_object.get("customer_details") or {}).get("email") or "Monthly Plan Customer"
        if customer_id and subscription_id and get_api_key_by_stripe_customer_id(customer_id) is None:
            record = create_api_key(
                customer_email,
                monthly_limit=MONTHLY_PLAN_ROUTE_LIMIT,
                source_label="monthly_plan",
                notes="Auto-provisioned by Stripe checkout.session.completed",
                plan="monthly_100",
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
            )
            logger.info(
                "Provisioned monthly-plan API key id=%s for stripe_customer=%s",
                record.get("id"),
                customer_id,
            )
            # Stash the raw key in Stripe Customer metadata for exactly one
            # pickup by /subscribe/success - we never persist it ourselves
            # (only its SHA-256 hash), and the success page clears this
            # field the moment it's displayed.
            try:
                stripe.Customer.modify(
                    customer_id,
                    metadata={"quantaroute_api_key": record["api_key"]},
                )
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Could not stash API key in Stripe customer metadata for {customer_id}: {e}"
                )

    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_id = data_object.get("id")
        status = data_object.get("status", "")
        record = get_api_key_by_stripe_subscription(subscription_id) if subscription_id else None
        if record is not None:
            should_be_active = event_type == "customer.subscription.updated" and status in {"active", "trialing"}
            set_api_key_active(record["id"], should_be_active)
            logger.info(
                "Set api_key id=%s active=%s from subscription %s status=%s",
                record["id"],
                should_be_active,
                subscription_id,
                status,
            )

    return JSONResponse(status_code=200, content={"received": True})


@app.post("/quantum/upload-csv", response_model=RouteResponse)
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    driver_name: str = "Driver",
    start_address: str | None = None,
    return_to_start: bool = False,
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")
    contents = await file.read()
    decoded = contents.decode("utf-8-sig")
    addresses = parse_csv_addresses(decoded)
    if len(addresses) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 addresses in CSV")
    if len(addresses) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 addresses per request")
    usage_response = enforce_usage_limit(request)
    if usage_response:
        return usage_response
    try:
        result = await optimise_route(
            addresses=addresses,
            driver_name=driver_name,
            start_address=start_address,
            return_to_start=return_to_start,
        )
    except RouteGeocodingError as e:
        logger.warning(f"CSV optimisation geocoding failed: {e.failed_addresses}")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GEOCODING_FAILED",
                "message": GEOCODING_HELP_MESSAGE,
                "failed_addresses": e.failed_addresses,
                "details": e.as_details(),
            },
        )
    route_id = record_route_history(
        driver_name=driver_name,
        result=result,
        source="web_csv",
        vehicle="van",
        optimise_for="distance",
        original_addresses=addresses,
        whatsapp_message=build_whatsapp_message(result.get("maps_url", ""), driver_name),
    )
    if route_id is not None:
        result["route_sheet_url"] = build_route_sheet_url(request, route_id)
    return RouteResponse(**{k: result.get(k) for k in RouteResponse.model_fields})

@app.get("/routes/history")
def route_history():
    return get_recent_routes(limit=50)


@app.get("/api/routes/recent")
def recent_routes(request: Request):
    return [
        build_recent_route_item(route, request)
        for route in get_recent_routes(limit=10)
    ]


@app.get("/route-sheet/{route_id}", response_class=HTMLResponse, include_in_schema=False)
def route_sheet(route_id: int):
    route = get_route_by_id(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route sheet not found")
    return HTMLResponse(build_route_sheet_html(route))


@app.post(
    "/api/optimise-route",
    response_model=PublicOptimiseRouteSuccess,
    tags=["Agent API"],
    summary="Optimise a small delivery route",
    description=(
        "Optimise 2-20 delivery stops for a UK courier or small operator, "
        "then return distance benchmarks, estimated saving, Google Maps URL, "
        "and a WhatsApp-ready driver message."
    ),
    responses={
        400: {
            "model": PublicOptimiseRouteErrorResponse,
            "description": "Invalid route input or geocoding failure.",
        },
        402: {
            "model": PublicOptimiseRouteErrorResponse,
            "description": "Free trial ended.",
        },
        401: {
            "model": PublicOptimiseRouteErrorResponse,
            "description": "Invalid or inactive API key.",
        },
        429: {
            "model": PublicOptimiseRouteErrorResponse,
            "description": "API key monthly limit exceeded.",
        },
        422: {
            "model": PublicOptimiseRouteErrorResponse,
            "description": "Invalid JSON or schema validation error.",
        },
    },
)
async def api_optimise_route(
    route_request: PublicOptimiseRouteRequest,
    request: Request,
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key",
        description="Optional during public testing. Paid/API access will require this later.",
    ),
):
    api_client: dict | None = None
    if x_api_key:
        api_key_valid, api_client, api_key_error_code, api_key_error = validate_and_record_api_key(x_api_key)
        if not api_key_valid:
            status_code = 429 if api_key_error_code == "MONTHLY_LIMIT_EXCEEDED" else 401
            return public_api_error(
                status_code,
                api_key_error_code or "INVALID_API_KEY",
                api_key_error or "Invalid or inactive API key.",
            )

    clean_start = clean_route_address(route_request.start)
    clean_end = clean_route_address(route_request.end or "")
    clean_stops, warnings = clean_public_stops(route_request.stops)
    long_addresses = too_long_addresses(
        [route_request.start, route_request.end or "", *route_request.stops]
    )

    if not clean_start:
        return public_api_error(
            400,
            "INVALID_START",
            "Start address is required.",
            ["Provide a depot, home base, town, postcode, or first pickup point."],
        )

    if long_addresses:
        return public_api_error(
            400,
            "ADDRESS_TOO_LONG",
            f"Addresses must be {MAX_PUBLIC_ADDRESS_LENGTH} characters or fewer.",
            [
                {
                    "address": address[:80],
                    "length": len(clean_route_address(address)),
                }
                for address in long_addresses
            ],
        )

    if len(clean_stops) < 2:
        return public_api_error(
            400,
            "INVALID_STOPS",
            "At least two unique valid delivery stops are required.",
            warnings
            or [
                "Add at least two different delivery stops. Do not use only empty or duplicate stops."
            ],
        )

    if len(clean_stops) > 20:
        return public_api_error(
            400,
            "TOO_MANY_STOPS",
            "The public API currently supports up to 20 delivery stops.",
            ["Split larger routes into smaller batches for now."],
        )

    usage_response = enforce_usage_limit(request) if api_client is None else None
    if usage_response:
        return public_api_error(
            402,
            "PAYMENT_REQUIRED",
            "Free trial ended. Please upgrade to continue at £1.99 per route, or subscribe to the monthly plan.",
            [UPGRADE_URL],
        )

    try:
        result = await optimise_route(
            addresses=clean_stops,
            driver_name="Driver",
            start_address=clean_start,
            return_to_start=False,
            end_address=clean_end or None,
        )
    except RouteGeocodingError as e:
        logger.warning(f"Public API geocoding failed: {e.failed_addresses}")
        return public_api_error(
            400,
            "GEOCODING_FAILED",
            GEOCODING_HELP_MESSAGE,
            e.as_details(),
        )
    except ValueError as e:
        logger.warning(f"Public API optimisation validation failed: {e}")
        return public_api_error(
            400,
            "GEOCODING_FAILED",
            "Could not geocode one or more addresses.",
            [str(e)],
        )
    except Exception as e:
        logger.error(f"Public API optimisation failed: {e}")
        return public_api_error(
            500,
            "OPTIMISATION_FAILED",
            "The route optimisation service could not complete this request.",
            [str(e)],
        )

    if result.get("geocoded_count", 0) < 2:
        return public_api_error(
            400,
            "GEOCODING_FAILED",
            "Could not geocode enough valid addresses to optimise the route.",
            result.get("failed_addresses", []),
        )

    if clean_end:
        result["maps_url"] = build_google_maps_url(
            result["ordered_addresses"],
            start_address=clean_start,
            end_address=clean_end,
        )

    original_distance = float(result.get("original_order_distance_km") or result.get("naive_distance_km") or 0)
    optimised_distance = float(result.get("final_selected_distance_km") or result.get("total_distance_km") or 0)
    distance_saved = round(max(original_distance - optimised_distance, 0.0), 2)
    estimated_saving_percent = float(result.get("fuel_saving_percent_vs_original") or result.get("fuel_saving_percent") or 0)
    estimated_saving_percent = max(round(estimated_saving_percent, 2), 0.0)
    google_maps_url = result.get("maps_url", "")
    whatsapp_message = build_whatsapp_message(google_maps_url, "Driver")

    response_warnings = public_route_warnings(route_request, result, warnings)
    if api_client is not None:
        client_source = api_client.get("source_label") or api_client.get("label") or "api_client"
        route_source = f"api_key:{client_source}"
    else:
        route_source = request.headers.get("x-quantaroute-source", "public_api").strip().lower() or "public_api"
        if route_source == "api":
            route_source = "public_api"
        if route_source not in {"public_api", "mcp", "web"}:
            route_source = "public_api"
    route_id = record_route_history(
        driver_name="API Agent",
        result=result,
        source=route_source,
        vehicle=route_request.vehicle,
        optimise_for=route_request.optimise_for,
        original_addresses=clean_stops,
        warnings=response_warnings,
        whatsapp_message=whatsapp_message,
    )
    route_sheet_url = build_route_sheet_url(request, route_id) if route_id is not None else None
    record_usage_event(
        route_id=route_id,
        api_key_id=api_client.get("id") if api_client else None,
        source=route_source,
        endpoint="/api/optimise-route",
        status="success",
        stops_count=len(clean_stops),
        distance_saved_km=distance_saved,
        estimated_saving_percent=estimated_saving_percent,
    )

    return {
        "success": True,
        "input_stop_count": len(clean_stops),
        "ordered_stops": build_public_ordered_stops(
            clean_start,
            result.get("ordered_addresses", []),
            clean_end or None,
        ),
        "original_distance_km": round(original_distance, 2),
        "optimised_distance_km": round(optimised_distance, 2),
        "distance_saved_km": distance_saved,
        "estimated_saving_percent": estimated_saving_percent,
        "algorithm_used": result.get("algorithm_used"),
        "google_maps_url": google_maps_url,
        "whatsapp_message": whatsapp_message,
        "route_sheet_url": route_sheet_url,
        **api_client_response_metadata(api_client),
        "warnings": response_warnings,
    }

@app.post("/quantum/route-optimise", response_model=RouteResponse)
async def route_optimise(route_request: RouteRequest, request: Request):
    if len(route_request.addresses) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 addresses")
    if len(route_request.addresses) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 addresses per request")
    usage_response = enforce_usage_limit(request)
    if usage_response:
        return usage_response
    try:
        result = await optimise_route(
            addresses=route_request.addresses,
            driver_name=route_request.driver_name,
            start_address=route_request.start_address,
            return_to_start=route_request.return_to_start,
        )
        route_id = record_route_history(
            driver_name=route_request.driver_name,
            result=result,
            source="web",
            vehicle="van",
            optimise_for="distance",
            original_addresses=route_request.addresses,
            whatsapp_message=build_whatsapp_message(
                result.get("maps_url", ""),
                route_request.driver_name,
            ),
        )
        if route_id is not None:
            result["route_sheet_url"] = build_route_sheet_url(request, route_id)
        return RouteResponse(**{k: result.get(k) for k in RouteResponse.model_fields})
    except RouteGeocodingError as e:
        logger.warning(f"Optimisation geocoding failed: {e.failed_addresses}")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GEOCODING_FAILED",
                "message": GEOCODING_HELP_MESSAGE,
                "failed_addresses": e.failed_addresses,
                "details": e.as_details(),
            },
        )
    except ValueError as e:
        logger.warning(f"Optimisation validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Optimisation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
