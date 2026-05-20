"""
QuantaRoute — FastAPI Main Entry Point
"""

import sys
import os
import csv
import io
import re
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services'))

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging

from services.route_builder import clean_route_address, optimise_route

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONTACT_EMAIL = "hi@quantaroute.co.uk"
SUPPORT_EMAIL = "hi@quantaroute.co.uk"

app = FastAPI(
    title="QuantaRoute API",
    description="Qiskit-powered quantum-inspired delivery route optimisation for UK couriers",
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

from database import get_recent_routes, init_db, record_allowed_route_use, save_route

init_db()
UPGRADE_URL = "https://quantaroute.onrender.com/pricing"


def record_route_history(driver_name: str, result: dict) -> None:
    try:
        save_route(driver_name=driver_name, result=result)
    except Exception as e:
        logger.error(f"Failed to save route history: {e}")


def get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_usage_limit(request: Request) -> JSONResponse | None:
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
            "detail": "Free trial ended. Please upgrade to continue at £1.99 per route.",
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
    stops_count: int
    geocoded_count: int
    failed_addresses: list[str]

@app.get("/health")
def health():
    return {"status": "ok", "service": "QuantaRoute API", "version": "1.0.0"}

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

@app.get("/pricing", include_in_schema=False)
def pricing_page():
    return frontend_file("landing.html")

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
    result = await optimise_route(
        addresses=addresses,
        driver_name=driver_name,
        start_address=start_address,
        return_to_start=return_to_start,
    )
    record_route_history(driver_name=driver_name, result=result)
    return RouteResponse(**{k: result[k] for k in RouteResponse.model_fields})

@app.get("/routes/history")
def route_history():
    return get_recent_routes(limit=50)

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
        record_route_history(driver_name=route_request.driver_name, result=result)
        return RouteResponse(**{k: result[k] for k in RouteResponse.model_fields})
    except ValueError as e:
        logger.warning(f"Optimisation validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Optimisation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
