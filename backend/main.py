"""
QuantaRoute — FastAPI Main Entry Point
"""

import sys
import os
import csv
import io
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services'))

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging

from services.route_builder import optimise_route

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="QuantaRoute API",
    description="Qiskit-powered quantum-inspired delivery route optimisation for UK couriers",
    version="1.0.0"
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

@app.get("/", include_in_schema=False)
def frontend():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(
        index_path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )

@app.get("/pricing", include_in_schema=False)
def pricing_page():
    return frontend()

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
    reader = csv.reader(io.StringIO(decoded))
    addresses = []
    for row in reader:
        if not row:
            continue
        first = row[0].strip()
        if not first:
            continue
        if first.lower() in {"address", "addresses", "stop", "stops"}:
            continue
        addresses.append(first)
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
