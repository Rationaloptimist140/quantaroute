"""
QuantaRoute — FastAPI Main Entry Point
"""

import sys
import os
import csv
import io

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services'))

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

from services.route_builder import optimise_route

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="QuantaRoute API",
    description="Quantum-powered delivery route optimisation for UK couriers",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class RouteRequest(BaseModel):
    addresses: list[str]
    driver_name: str = "Driver"

class RouteResponse(BaseModel):
    optimised_order: list[int]
    ordered_addresses: list[str]
    total_distance_km: float
    naive_distance_km: float
    fuel_saving_percent: float
    maps_url: str
    whatsapp_url: str
    stops_count: int
    geocoded_count: int
    failed_addresses: list[str]

@app.get("/health")
def health():
    return {"status": "ok", "service": "QuantaRoute API", "version": "1.0.0"}

@app.post("/quantum/upload-csv", response_model=RouteResponse)
async def upload_csv(file: UploadFile = File(...), driver_name: str = "Driver"):
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
    result = await optimise_route(addresses=addresses, driver_name=driver_name)
    return RouteResponse(**{k: result[k] for k in RouteResponse.model_fields})

@app.post("/quantum/route-optimise", response_model=RouteResponse)
async def route_optimise(request: RouteRequest):
    if len(request.addresses) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 addresses")
    if len(request.addresses) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 addresses per request")
    try:
        result = await optimise_route(
            addresses=request.addresses,
            driver_name=request.driver_name
        )
        return RouteResponse(**{k: result[k] for k in RouteResponse.model_fields})
    except Exception as e:
        logger.error(f"Optimisation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)