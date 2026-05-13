# QuantaRoute Project Notes

## Current Goal

QuantaRoute is a FastAPI + frontend app for UK courier route optimisation. The main product message is practical fuel savings: paste or upload stops, optionally set a start address/depot, reorder delivery stops using real road-network distances, show the fuel saving percentage, and provide Google Maps and WhatsApp links before the driver sets off.

Live app: https://quantaroute.onrender.com

GitHub repo: https://github.com/Rationaloptimist140/quantaroute

Source pitch file reviewed: `C:\Users\rw718\Desktop\QuantaRoute-USP-Pitch.pdf`

## Product Positioning / USP

- Built for UK couriers and delivery drivers.
- Browser-first: no app download, no installation, no account setup required for the basic route flow.
- Core promise: road-based, fuel-saving route optimisation for drivers and small fleets. Qiskit remains supporting technical credibility for selected route sizes, not the headline sales claim.
- Route output should always emphasise:
  - optimised delivery order
  - optional start/depot address for Google Maps directions
  - fuel saving percentage
  - total distance
  - direct Google Maps link
  - WhatsApp share link
- Differentiators from the pitch:
  - Qiskit QAOA quantum simulation for 8-20 stops, exact brute force for smaller routes, nearest-neighbour fallback for larger routes.
  - Real road-network distances, not straight-line estimates.
  - Optional start address/depot and optional return-to-start in Google Maps directions.
  - CSV upload or pasted stops.
  - Works on mobile and desktop browsers.
  - Built in the UK for UK postcode routing.
- Pricing positioning from the pitch:
  - Proposed price: `£1.99 per optimised route`.
  - Proposed launch offer: free first month.
  - No subscription lock-in and no per-driver fees.
  - Competitor framing: Routific, OptimoRoute, Zeo, and enRoute use monthly subscriptions and/or app-first workflows.
- Current pricing implementation:
  - Free for the first month, with usage tracked by client IP address.
  - After 30 days, non-paying users receive HTTP `402` with an upgrade link.
  - Payment collection is still a placeholder; Stripe checkout is marked as coming soon.

## Pitch Claims To Validate

- Pitch says real tests showed:
  - 5 stops in Plymouth/Exeter: `3.74%` fuel saved.
  - 30 stops across South West England: `13.62%` fuel saved.
- Homepage now avoids the unsupported "up to 49%" headline and focuses on smarter route optimisation, road distances, and visible fuel savings.
- SQLite route history is now implemented locally/session-locally.

## Files Changed

- `requirements.txt` - updated Python 3.14-compatible dependency pins.
- `backend/services/requirements.txt` - kept service dependency pins aligned.
- `render.yaml` - configured Render to run from `backend` with `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- `backend/main.py` - serves frontend at `/` and `/pricing`, static assets at `/assets`, no-store frontend cache headers, route validation handling, optional start/depot request fields, route history, and free-trial enforcement.
- `backend/database.py` - SQLite route history storage, automatic database initialisation, save/list helpers, and IP-based usage tracking.
- `backend/services/geocoder.py` - robust UK postcode geocoding using active postcodes, terminated postcodes, outward codes, then Nominatim GB fallback.
- `backend/services/route_builder.py` - clearer error when too few stops can be geocoded, route-quality baseline reporting, optional start/depot Google Maps routing, return-to-start support, and cleaned addresses for API results, Google Maps links, and WhatsApp links.
- `frontend/index.html` - complete mobile-first Premium White frontend, live Render API URL, fuel-saving road-based messaging, start address and return-to-start inputs, pricing banner/card, competitor table, `402` upgrade message, results info line, and collapsible route history.
- `frontend/result.html` - Premium White result-page shell with fuel-saving and road-network messaging.
- `frontend/pricing.html` - Premium White pricing page with fuel-saving, simplicity, and road-based routing messaging.
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
- SQLite `users` table tracks first use, route count, and paying status by IP address.
- Backend blocks expired free-trial users with HTTP `402` and the frontend shows a friendly upgrade prompt.
- CSV row numbers, surrounding quote marks, and trailing commas are stripped from displayed stops, API `ordered_addresses`, Google Maps directions links, and WhatsApp share links.
- Google Maps directions can start from a cleaned start/depot address and optionally append that same start address at the end for round trips. The start address is not displayed as a numbered delivery stop.

## Remaining Issues

- Route quality depends on public external services: `api.postcodes.io`, Nominatim, and OSRM.
- Some postcode/outcode results may be approximate, especially terminated or outward-only inputs.
- Fuel saving percent is based on the current naive route comparison and can be low for already efficient input order.
- Route history uses SQLite on the local/Render filesystem. Render free-tier filesystems are ephemeral, so production history can reset after restarts/redeploys.
- Usage tracking currently uses IP address only; this is simple but not robust for shared networks, VPNs, or users with changing IPs.
- Stripe/payment collection is not implemented yet; the pricing section currently says payment is coming soon.
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

Pricing page:

```powershell
Invoke-WebRequest -Uri "https://quantaroute.onrender.com/pricing" -UseBasicParsing
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
- Tables: `routes` for route history and `users` for free-trial usage tracking.
