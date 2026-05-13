# QuantaRoute Project Notes

## Current Goal

QuantaRoute is a FastAPI + single-page frontend app for UK courier route optimisation. The main product message is fuel savings: show an optimised route order, fuel saving percentage, total distance, Google Maps link, WhatsApp share link, and recent route history.

Live app: https://quantaroute.onrender.com

GitHub repo: https://github.com/Rationaloptimist140/quantaroute

Source pitch file reviewed: `C:\Users\rw718\Desktop\QuantaRoute-USP-Pitch.pdf`

## Product Positioning / USP

- Built for UK couriers and delivery drivers.
- Browser-first: no app download, no installation, no account setup required for the basic route flow.
- Core promise: Qiskit-powered, quantum-inspired route optimisation that reduces fuel cost.
- Route output should always emphasise:
  - optimised delivery order
  - fuel saving percentage
  - total distance
  - direct Google Maps link
  - WhatsApp share link
- Differentiators from the pitch:
  - Qiskit QAOA quantum simulation for 8-20 stops, exact brute force for smaller routes, nearest-neighbour fallback for larger routes.
  - CSV upload or pasted stops.
  - Works on mobile and desktop browsers.
  - Built in the UK for UK postcode routing.
- Pricing positioning from the pitch:
  - Proposed price: `£1.99 per optimised route`.
  - Proposed launch offer: free first month.
  - No subscription lock-in and no per-driver fees.
  - Competitor framing: Routific, OptimoRoute, Zeo, and enRoute use monthly subscriptions and/or app-first workflows.

## Pitch Claims To Validate

- Pitch says real tests showed:
  - 5 stops in Plymouth/Exeter: `3.74%` fuel saved.
  - 30 stops across South West England: `13.62%` fuel saved.
- Frontend currently says "Save up to 49% on fuel costs"; keep this only if there is supporting test data or change it to a proven claim.
- SQLite route history is now implemented locally/session-locally.

## Files Changed

- `requirements.txt` - updated Python 3.14-compatible dependency pins.
- `backend/services/requirements.txt` - kept service dependency pins aligned.
- `render.yaml` - configured Render to run from `backend` with `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- `backend/main.py` - serves frontend at `/`, static assets at `/assets`, no-store frontend cache headers, route validation handling.
- `backend/database.py` - SQLite route history storage, automatic database initialisation, save/list helpers.
- `backend/services/geocoder.py` - robust UK postcode geocoding using active postcodes, terminated postcodes, outward codes, then Nominatim GB fallback.
- `backend/services/route_builder.py` - clearer error when too few stops can be geocoded.
- `frontend/index.html` - complete mobile-first dark quantum-inspired frontend, live Render API URL, fuel-saving hero messaging, comparison strip, results info line, and collapsible route history.
- `frontend/assets/quantaroute-logo.svg` - cyan atom + location pin logo.
- `.gitignore` - ignores local temp/package/venv artifacts.

## Bugs Fixed

- `numpy==1.26.4` failed on Python 3.14; changed to `numpy>=2.2.0,<3`.
- Older `pydantic` and `qiskit-aer` pins required native builds on Python 3.14; updated to compatible wheel versions.
- Render `/` returned `{"detail":"Not Found"}`; FastAPI now serves `frontend/index.html`.
- Frontend cached old `localhost:8000` text; page is served with `Cache-Control: no-store`.
- Postcode-only requests could fail with `Need at least 2 geocoded addresses`; geocoder now supports active, terminated, and outward UK postcodes.
- Backend now returns friendlier `400` errors for geocoding validation failures instead of generic `500`.
- SQLite route history now initialises automatically and saves each successful JSON or CSV route optimisation.
- `GET /routes/history` returns the last 50 saved routes.

## Remaining Issues

- Route quality depends on public external services: `api.postcodes.io`, Nominatim, and OSRM.
- Some postcode/outcode results may be approximate, especially terminated or outward-only inputs.
- Fuel saving percent is based on the current naive route comparison and can be low for already efficient input order.
- Route history uses SQLite on the local/Render filesystem. Render free-tier filesystems are ephemeral, so production history can reset after restarts/redeploys.
- Payment/pricing flow for `£1.99 per route` and free first month is not implemented yet.
- The "up to 49%" marketing claim needs supporting data or should be adjusted to match proven results.
- Render free tier can cold start, so first request may be slow.
- The Render API key previously appeared in a screenshot and should be revoked/regenerated.

## Deployment Steps

1. Commit changes to `master`.
2. Push to GitHub:

   ```powershell
   git push origin master
   ```

3. Render service:
   - Name: `quantaroute`
   - Root directory: `backend`
   - Build command: `pip install -r ../requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Health check: `/health`

4. Render usually auto-deploys on push. If it lags, trigger a manual deploy from the Render dashboard or API.

## Important Commands

Run backend locally:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute\backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-WebRequest -Uri "https://quantaroute.onrender.com/health" -UseBasicParsing
```

Route history:

```powershell
Invoke-RestMethod -Method Get -Uri "https://quantaroute.onrender.com/routes/history"
```

Route optimisation smoke test:

```powershell
$body = @{
  addresses = @("SW1A 1AA", "EC1A 1BB", "W1A 0AX", "M1 1AE", "B1 1AA")
  driver_name = "Driver"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "https://quantaroute.onrender.com/quantum/route-optimise" `
  -ContentType "application/json" `
  -Body $body
```

Check frontend HTML is current:

```powershell
$r = Invoke-WebRequest -Uri "https://quantaroute.onrender.com/" -UseBasicParsing
$r.Content.Contains("https://quantaroute.onrender.com/quantum/route-optimise")
$r.Content.Contains("localhost:8000")
```

Current known-good production result for the smoke-test postcodes:

- `geocoded_count = 5`
- `failed_addresses = []`
- `maps_url` is returned.

Local SQLite database:

- File path: `backend/quantaroute.db`
- This file is ignored by Git.
- It is created automatically on startup by `backend/database.py`.
