# QuantaRoute Project Notes

## Current Goal

QuantaRoute is a FastAPI + frontend app for UK courier route optimisation. The main product message is practical dispatch: turn delivery stops into a driver-ready Google Maps route in seconds, estimate fuel/distance savings against the entered order, and prepare WhatsApp-ready driver sharing with no app install.

The product is now being shaped as both a normal SaaS web tool for humans and an agent-ready API/MCP-compatible tool for AI assistants and business agents.

Current internal benchmark mode records route-quality evidence for each successful optimisation: original input order distance, nearest-neighbour distance, final selected route distance, and fuel saving versus the original order.

The working app and marketing page are now separated: `frontend/index.html` is the fast route-optimiser tool, while `frontend/landing.html` holds the courier-first explainer, pricing, and comparison copy.

Live app: https://quantaroute.co.uk

Render URL: https://quantaroute.onrender.com

GitHub repo: https://github.com/Rationaloptimist140/quantaroute

Contact/support email: `hi@quantaroute.co.uk`

Source pitch file reviewed: `C:\Users\rw718\Desktop\QuantaRoute-USP-Pitch.pdf`

## Product Positioning / USP

- Built for UK couriers and delivery drivers.
- Browser-first: no app download, no installation, no account setup required for the basic route flow.
- Core promise: road-based, fuel-saving route optimisation for drivers and small fleets. Qiskit remains an experimental/internal optimisation module, not the live route-selection promise.
- API-first promise: agents can submit a start point, 2-20 delivery stops, optional end point, vehicle, and optimisation preference, then receive ordered stops, benchmark distances, estimated saving, a Google Maps URL, WhatsApp message, and warnings.
- MCP promise: a runnable local stdio MCP server now exposes `optimise_delivery_route` and calls the same public FastAPI endpoint.
- API-key foundation: `X-API-Key` is optional during public testing; valid keys are hashed at rest, usage-counted by month, can enforce optional monthly limits, and can tag API/MCP route history for future paid access and rate limits. This same monthly_limit mechanism now backs the new monthly subscription plan (see below).
- The working app should keep the route form visible immediately on load. Marketing/explainer content belongs on `frontend/landing.html`.
- Route output should always emphasise:
  - optimised delivery order
  - optional start/depot address for Google Maps directions
  - fuel saving percentage
  - optional collapsed benchmark details comparing input order, nearest-neighbour, and final route
  - total distance
  - direct Google Maps link
  - WhatsApp share link
  - printable route sheet link
- Differentiators from the pitch:
  - Live route selection uses exact brute force for small routes and nearest-neighbour heuristics for larger routes to keep Render/free-tier requests responsive.
  - Qiskit QAOA simulation remains in the codebase for internal experimentation, but is not used as the live default after stress testing showed larger QAOA jobs can exceed request limits.
  - Real road-network distances, not straight-line estimates.
  - Optional start address/depot and optional return-to-start in Google Maps directions.
  - CSV upload or pasted stops.
  - Works on mobile and desktop browsers.
  - Built in the UK for UK postcode routing.
- Pricing positioning from the pitch:
  - Proposed price: `£1.99 per optimised route`.
  - Proposed launch offer: free first month.
  - No subscription lock-in and no per-driver fees for the pay-per-route tier.
  - New (2026-07-17): a monthly plan at `£1.99/month for up to 100 routes` for couriers who run routes most days and want predictable cost, offered alongside pay-per-route rather than replacing it.
  - Competitor framing: Routific, OptimoRoute, Zeo, and enRoute use monthly subscriptions and/or app-first workflows.
- Current pricing implementation:
  - Free for the first month, with usage tracked by client IP address.
  - After 30 days, non-paying users receive HTTP `402` with an upgrade link.
  - Payment collection is still a placeholder; Stripe checkout for the monthly plan is in progress. Pay-per-route Stripe checkout is deliberately deferred.
  - The monthly plan is currently provisioned manually as an API key with `monthly_limit=100` (see "Monthly Subscription Plan" below); self-serve Stripe checkout is the next step once Stripe keys are configured.

## Admin / Owner Bypass (2026-07-17)

The free-trial gate blocks any IP identifier 30 days after its first use, with no owner exception. The owner's own IP got permanently 402'd once its original test traffic aged past 30 days (site went live 2026-05-13). Added a durable override entirely via Render env vars, no code redeploy needed to add/rotate access:

- `ADMIN_KEY`: shared secret. Visiting any URL once with `?admin_key=<value>` sets a signed, year-long `httponly` cookie (`qr_admin`) that bypasses the trial/paywall gate on all later requests from that browser. Also accepted as an `X-Admin-Key` header for scripts/API use.
- `ADMIN_BYPASS_IPS`: optional comma-separated static IP allowlist, checked as a fallback.
- Implemented in `backend/main.py`: `is_admin_request()` + an HTTP middleware that sets the cookie, checked first thing inside `enforce_usage_limit()` before the existing 30-day/`is_paying` logic runs. Applies uniformly to `/quantum/route-optimise`, `/quantum/upload-csv`, and the public `/api/optimise-route` (when no separate API key already grants access).
- `scripts/mark_paying.py` is a one-time stopgap: flips a specific already-recorded identifier's `is_paying` flag directly in whichever DB backend is active, for when you need to unblock an IP right now without waiting on env vars to propagate.
- `ADMIN_KEY` must be set in the Render service environment before this works in production; without it the bypass paths are inert (`is_admin_request` returns `False`) and behaviour is unchanged from before.

## Monthly Subscription Plan (2026-07-17)

Rather than build a second, parallel subscription system, the new "£1.99/month for up to 100 routes" plan reuses the existing `quantaroute_api_keys` table, which already had `monthly_limit` + `usage_count_current_month` — exactly the shape a 100-routes/month plan needs.

- Added columns: `plan`, `stripe_customer_id`, `stripe_subscription_id` on `quantaroute_api_keys` (both SQLite and Postgres schema paths in `backend/database.py`), plus `get_api_key_by_stripe_subscription()` and `set_api_key_active()` helpers so a future Stripe webhook can activate/deactivate the linked key without a second source of truth.
- `create_api_key()` now accepts optional `plan`, `stripe_customer_id`, `stripe_subscription_id` kwargs.
- Today, before Stripe checkout is wired up, a monthly subscriber is provisioned manually: run `scripts/create_api_key.py --label "<customer>" --monthly-limit 100` (optionally pass `plan="monthly_100"` once the script is extended) and hand them the key.
- `frontend/pricing.html` now has a third pricing card for the Monthly Plan; its CTA currently mails `hi@quantaroute.co.uk` rather than a live checkout, since Stripe keys/price object are not yet confirmed as available.
- **Not yet built**: the actual Stripe Checkout Session endpoint and webhook handler (`checkout.session.completed`, `customer.subscription.updated`/`deleted`) that would provision/activate/deactivate the linked API key automatically. Needs `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and a recurring £1.99/month Stripe Price ID before that can ship. `stripe` was added to `requirements.txt` in preparation.
- Per-route (pay-as-you-go) Stripe checkout remains explicitly out of scope for now, per product decision on 2026-07-17.

## Pitch Claims To Validate

- Pitch says real tests showed:
  - 5 stops in Plymouth/Exeter: `3.74%` fuel saved.
  - 30 stops across South West England: `13.62%` fuel saved.
- Homepage now avoids the unsupported "up to 49%" headline and focuses on smarter route optimisation, road distances, and visible fuel savings.
- Route history uses Postgres in production when `DATABASE_URL` is set, with SQLite kept as the local development fallback.

## Files Changed

- `requirements.txt` - updated Python 3.14-compatible dependency pins, added `psycopg[binary]` for Postgres route-history persistence, and added `stripe` in preparation for the monthly-plan checkout/webhook work.
- `backend/services/requirements.txt` - kept service dependency pins aligned, including the Postgres driver.
- `render.yaml` - configured Render to run from `backend` with `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- `backend/main.py` - serves the working app at `/` and `/index.html`, the marketing page at `/landing`, `/landing.html`, static assets at `/assets`, no-store frontend cache headers, route validation handling, CSV upload address extraction, contact/support email constants, road-network API description, optional start/depot request fields, route history, and free-trial enforcement.
- `backend/main.py` - added `POST /api/optimise-route` for agent/public API usage, structured API success/error models, optional `X-API-Key` handling, monthly-limit responses, `GET /llms.txt`, improved OpenAPI schema examples, API validation error handling, duplicate-stop cleanup, 20-stop limit handling, route-history saving for API requests, usage-event recording, and a health-check build marker.
- `backend/main.py` - public API, CSV upload, and web optimiser now return clear structured geocoding errors that identify the failed address and say: "Could not find this address. Try adding postcode, city, or full business address."
- `backend/main.py` (2026-07-17) - added `ADMIN_KEY`/`ADMIN_BYPASS_IPS` admin bypass (query param, `X-Admin-Key` header, or signed cookie) checked first inside `enforce_usage_limit`; `/pricing` now correctly serves `frontend/pricing.html` instead of `frontend/landing.html`; `/health/deep` reports `admin_bypass_configured`.
- `backend/database.py` - dual SQLite/Postgres route history storage, benchmark metric persistence, automatic table initialisation, API-key hashing/storage/monthly-limit helpers, structured usage-event helpers, save/list/export/lookup helpers, and IP-based usage tracking.
- `backend/database.py` (2026-07-17) - added `plan`, `stripe_customer_id`, `stripe_subscription_id` columns on `quantaroute_api_keys`; added `get_api_key_by_stripe_subscription()`, `set_api_key_active()`, and `mark_identifier_as_paying()` helpers.
- `backend/services/geocoder.py` - robust UK postcode geocoding using active postcodes, terminated postcodes, outward codes, Nominatim GB fallback, and Photon fallback for commercial/place-name addresses.
- `backend/services/geocoder.py` - Nominatim requests now include the QuantaRoute contact email in the User-Agent so the hosted service is identifiable to public geocoding infrastructure.
- `backend/services/route_builder.py` - clearer error when too few stops can be geocoded, filters failed/malformed geocodes before routing, live-safe route selection, route-quality benchmark reporting, optional start/depot Google Maps routing, return-to-start support, and cleaned addresses for API results, Google Maps links, and WhatsApp links.
- `backend/services/route_builder.py` - extended shared Google Maps URL building to support optional end addresses and added a reusable WhatsApp message helper for the public API/MCP layer.
- `backend/services/route_builder.py` - reported original, nearest-neighbour, and final route distances now include optional start and end/return-to-start points instead of only delivery stops.
- `frontend/index.html` - displays structured geocoding failures with the exact failed stop and helpful postcode/full-address guidance.
- `backend/services/route_sheet.py` - dependency-free plain-text route sheet helper kept for future downloadable route sheet/PDF work.
- `backend/services/route_sheet.py` - printable HTML route sheet renderer with summary, numbered stops, Google Maps link, WhatsApp driver message, print button, and safety note.
- `backend/services/road_matrix.py` - OSRM/Haversine distance matrix builder with coordinate validation and fallback handling for incomplete OSRM responses.
- `frontend/index.html` - clean mobile-first Premium White route optimiser tool with live Render API URL, driver/start/return-to-start/stops inputs, multi-column CSV upload cleanup, results, Google Maps and WhatsApp actions, collapsed benchmark details, route history, and subtle `About QuantaRoute`/contact links.
- `frontend/index.html` - route results now include an `Open Route Sheet` action when `route_sheet_url` is returned.
- `frontend/landing.html` - separate Premium White marketing page with courier-first hero, how-it-works route-selection explainer, Plymouth courier scenario, benchmark proof example, comparison copy, pricing, contact email, and a `Try QuantaRoute free` link back to the app.
- `frontend/landing.html` - updated with API-first/product positioning, 20-stop Plymouth proof section, audience list, simplified how-it-works steps, agent-ready API/MCP section, safer savings language, and current pricing/payment copy.
- `frontend/landing.html` - links to `developers.html`, `/openapi.json`, and `/llms.txt` for public developer/agent access.
- `frontend/developers.html` - public static developer page explaining `POST /api/optimise-route`, MCP tool `optimise_delivery_route`, API request/response examples, local MCP setup, estimated-savings safety note, and current free-to-test/Stripe-not-active status.
- `frontend/developers.html` - polished developer subtitle, added response explanation, optional API-key docs, duplicate depot warning, and public status section for API/MCP/payments/PDF/time/vehicle routing.
- `examples/` - added a Plymouth API request JSON, live PowerShell curl example, and Claude Desktop/Cursor/Codex-style MCP config.
- `frontend/result.html` - Premium White result-page shell with fuel-saving and road-network messaging.
- `frontend/pricing.html` - Premium White pricing page with fuel-saving, simplicity, and road-based routing messaging.
- `frontend/pricing.html` (2026-07-17) - added a third "Monthly Plan" card (£1.99/month, up to 100 routes) alongside the Free trial and Pay As You Go cards; comparison table and beta note updated to mention both pricing paths.
- `frontend/assets/quantaroute-logo.svg` - cyan atom + location pin logo.
- `.gitignore` - ignores local temp/package/venv artifacts.
- `mcp/server.ts` - runnable stdio MCP server using the official TypeScript MCP SDK, exposing `optimise_delivery_route`, calling the FastAPI public API instead of duplicating optimisation logic, tagging requests with `X-QuantaRoute-Source: mcp`, and optionally forwarding `QUANTAROUTE_API_KEY`.
- `mcp/README.md` - documents optional `QUANTAROUTE_API_KEY` usage.
- `scripts/create_api_key.py` - local/dev CLI helper that creates a raw API key once and stores only its SHA-256 hash.
- `scripts/export_route_history.py` - local/admin CLI backup helper that exports route history from Postgres or SQLite to timestamped JSON and CSV files.
- `scripts/mark_paying.py` (2026-07-17, new) - one-time stopgap CLI to mark a specific identifier (IP) as paying, bypassing the 30-day free trial for that identifier without waiting on env var propagation.
- `mcp/package.json`, `mcp/package-lock.json`, `mcp/tsconfig.json`, `mcp/README.md`, `mcp/test-api-call.ts`, `mcp/test-mcp-call.ts` - package scripts, build config, MCP config examples, and direct/MCP call tests.
- `README.md` - refreshed API-first documentation, endpoint example, agent-ready direction, pricing, and safety language.
- `README.md` (2026-07-17) - added "Admin / Owner Bypass" section documenting `ADMIN_KEY`/`ADMIN_BYPASS_IPS`/`scripts/mark_paying.py`, and updated the Pricing section to mention the monthly plan.
- `requirements-dev.txt` - Python dev/test dependencies.
- `tests/` - pytest coverage for the public API success/error/docs paths, optional API-key success/error paths, start/end distance reporting, route sheets, SQLite fallback route-history persistence, route-history export, and hashed API-key storage.

## Bugs Fixed

- `numpy==1.26.4` failed on Python 3.14; changed to `numpy>=2.2.0,<3`.
- Older `pydantic` and `qiskit-aer` pins required native builds on Python 3.14; updated to compatible wheel versions.
- Render `/` returned `{"detail":"Not Found"}`; FastAPI now serves `frontend/index.html`.
- Frontend cached old `localhost:8000` text; page is served with `Cache-Control: no-store`.
- Postcode-only requests could fail with `Need at least 2 geocoded addresses`; geocoder now supports active, terminated, and outward UK postcodes.
- If a full postcode lookup fails, the geocoder now tries the outward code before falling back to Nominatim, reducing large-batch timeout risk.
- Backend now returns friendlier `400` errors for geocoding validation failures instead of generic `500`.
- Failed or malformed geocoder results are now filtered before distance-matrix work, avoiding `NoneType` crashes when an address cannot be geocoded.
- OSRM `distances: null` or incomplete distance matrices now fall back to Haversine instead of crashing.
- Live route selection no longer enters QAOA for 8-20 stop jobs; stress testing showed larger QAOA simulation could exceed request timeouts or lock a free-tier worker.
- Route history now initialises automatically in Postgres or SQLite and saves each successful JSON or CSV route optimisation.
- `GET /routes/history` returns the last 50 saved routes.
- The `users` table tracks first use, route count, and paying status by IP address in whichever storage backend is active.
- Backend blocks expired free-trial users with HTTP `402` and the frontend shows a friendly upgrade prompt.
- **The 30-day free-trial block had no exception for the site owner** — any IP whose first use was more than 30 days ago got permanently 402'd. Fixed 2026-07-17 with the `ADMIN_KEY`/`ADMIN_BYPASS_IPS` admin bypass in `backend/main.py`.
- **`/pricing` was silently serving `frontend/landing.html` instead of `frontend/pricing.html`**, so the dedicated pricing page (and its new Monthly Plan card) was never actually reachable at `/pricing`. Fixed 2026-07-17 in `backend/main.py`.
- CSV row numbers, surrounding quote marks, and trailing commas are stripped from displayed stops, API `ordered_addresses`, Google Maps directions links, and WhatsApp share links.
- Multi-column CSV uploads now extract business name + address columns and ignore stop numbers, postcode-only fields, and order details so stop names display cleanly.
- Google Maps directions can start from a cleaned start/depot address and optionally append that same start address at the end for round trips. The start address is not displayed as a numbered delivery stop.
- API responses and route history now include benchmark fields for original input order distance, nearest-neighbour distance, final selected route distance, and fuel saving versus original order.
- Frontend results now show a collapsed "Benchmark details" section when benchmark API fields are available.
- Public API endpoint `POST /api/optimise-route` now returns structured success JSON and structured `success: false` error JSON for invalid route input, over-20-stop requests, payment/trial blocks, and geocoding/optimisation failures.
- Successful route optimisation responses can now include `route_sheet_url`, using the saved route history ID from Postgres or SQLite.
- `GET /route-sheet/{route_id}` renders a printable driver route sheet from saved route history.
- Production route history can persist across Render redeploys when `DATABASE_URL` points to Postgres; local development still falls back to `backend/quantaroute.db`.
- Optional `X-API-Key` support is now implemented for `POST /api/optimise-route`. Valid keys update `last_used_at`, `month_key`, and `usage_count_current_month`; invalid or inactive keys return structured `401` errors; keys over their monthly limit return structured `429` errors.
- Raw API keys are not stored; `quantaroute_api_keys.key_hash` stores a SHA-256 hash.
- Successful public API calls record structured rows in `quantaroute_usage_events` with route ID, API key ID when present, source, endpoint, status, stops count, distance saved, and estimated saving percentage.
- Public no-key API testing still works while payments and paid API access are being prepared.
- MCP requests can optionally use `QUANTAROUTE_API_KEY` and are tagged as MCP/API-client traffic.
- Public API has non-blocking future TODOs for rate limiting and per-route billing, plus basic abuse protection for very long addresses and duplicate-only/empty stop lists.
- `/openapi.json` includes the agent route endpoint and request/response schemas.
- `/llms.txt` explains QuantaRoute for AI agents and LLMs.
- `/developers.html` is served as a public developer page and linked from the landing page.
- Public geocoding requests now use an identifiable User-Agent with the support email and a Photon fallback to reduce hosted commercial-address geocoder failure risk.
- Geocoding failures now identify the failed address instead of silently omitting it from a successful route.
- Reported distance metrics now include start/depot and optional end/return-to-start points when provided.
- MCP can now be run locally and tested with a real MCP client/server call.
- Formal pytest coverage now checks public API success, invalid JSON, over-20-stop rejection, failed geocoding, Google Maps URL, WhatsApp message, `/llms.txt`, `/openapi.json`, and route-builder start/end distance reporting.

## Remaining Issues

- Route quality depends on public external services: `api.postcodes.io`, Nominatim, and OSRM.
- Some postcode/outcode results may be approximate, especially terminated or outward-only inputs.
- Fuel saving percent is based on the current naive route comparison and can be low for already efficient input order.
- Name-only commercial stops can still fail in hosted geocoding; full business addresses with UK postcodes are much more reliable.
- `optimise_for = "time"` is accepted for API compatibility, but current routing still optimises for distance and returns a warning.
- `vehicle` is accepted for API compatibility, but current estimates use the existing van-style routing assumptions and return a warning for non-van values.
- Full PDF generation is still a follow-up; current route sheets use printable HTML and browser print-to-PDF.
- Route sheets use persistent Postgres route IDs when `DATABASE_URL` is configured.
- PDF export is not implemented; users can print the HTML route sheet or use browser print-to-PDF.
- If `DATABASE_URL` is missing in production, route history falls back to SQLite on the local/Render filesystem. Render free-tier filesystems are ephemeral, so old route sheet URLs can reset without Postgres.
- Usage tracking currently uses IP address only; this is simple but not robust for shared networks, VPNs, or users with changing IPs. `ADMIN_KEY` sidesteps this for the owner specifically; it does not fix it for regular users.
- API-key monthly limits are enforced when `monthly_limit` is set. A null monthly limit is treated as unlimited.
- Unauthenticated public API traffic is still allowed and not fully rate-limited yet.
- API keys are not mapped to Stripe customers/subscriptions in an automated way yet — `stripe_customer_id`/`stripe_subscription_id` columns exist but nothing writes to them until the checkout/webhook endpoints are built.
- Stripe/payment collection is not implemented yet; the pricing page currently sends Monthly Plan signups to email instead of live checkout, and pay-per-route checkout is explicitly deferred.
- Self-serve Stripe Checkout for the monthly plan needs `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and a recurring £1.99/month Price ID before it can ship — not yet confirmed as available.
- The "up to 49%" marketing claim needs supporting data or should be adjusted to match proven results.
- Render free tier can cold start, so first request may be slow.
- The Render API key previously appeared in a screenshot and should be revoked/regenerated.
- Route-history backups are manual for now; run `scripts/export_route_history.py` before changing storage or before a free Render Postgres instance expires.
- `ADMIN_KEY` must be set in the Render environment for the admin bypass to do anything; until then `is_admin_request()` always returns `False` and behaviour is unchanged.

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
   - Production persistence: create a Render Postgres database and set the web service environment variable `DATABASE_URL` to its internal database URL.
   - New env vars (2026-07-17): `ADMIN_KEY` (required for the owner bypass to work), `ADMIN_BYPASS_IPS` (optional). Stripe env vars (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_MONTHLY`) once the checkout/webhook endpoints are built.

4. Render usually auto-deploys on push. If it lags, trigger a manual deploy from the Render dashboard or API.

5. On startup, `backend/database.py` creates or extends the namespaced `quantaroute_route_history`, `quantaroute_api_keys`, and `quantaroute_usage_events` tables automatically. No manual migration command is currently required.

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

Route history backup export:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
python scripts\export_route_history.py --output-dir exports --format both --base-url https://quantaroute.co.uk
```

Route history backup export against Postgres:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
$env:DATABASE_URL="postgresql://user:password@host:5432/database"
python scripts\export_route_history.py --output-dir exports --format both --base-url https://quantaroute.co.uk
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

Agent/public API smoke test:

```powershell
$body = @{
  start = "Plymouth, UK"
  stops = @(
    "Drake Circus Shopping Centre, Plymouth",
    "Royal William Yard, Plymouth",
    "Plymouth Market, Plymouth",
    "Plymouth Railway Station, Plymouth"
  )
  end = "Plymouth, UK"
  vehicle = "van"
  optimise_for = "distance"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "https://quantaroute.co.uk/api/optimise-route" `
  -ContentType "application/json" `
  -Body $body
```

Create a local/dev API key:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
python scripts\create_api_key.py --label "Courier Bot" --monthly-limit 1000 --source-label courier_bot
```

Important: running `scripts/create_api_key.py` locally without `DATABASE_URL` writes the key to local SQLite at `backend/quantaroute.db`, not live Render Postgres. Local SQLite keys will not work against production.

Create a production API key by running the local script with production `DATABASE_URL` set:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
$env:DATABASE_URL="postgresql://user:password@host:5432/database"
python scripts\create_api_key.py --label "Rana test key" --monthly-limit 100
$env:DATABASE_URL=$null
```

Or use a Render shell if available:

```bash
# Repository root:
python scripts/create_api_key.py --label "Rana test key" --monthly-limit 100

# backend rootDir:
python ../scripts/create_api_key.py --label "Rana test key" --monthly-limit 100
```

Use a key with the public API:

```powershell
$headers = @{ "X-API-Key" = "qr_your_key_here" }
Invoke-RestMethod -Method Post `
  -Uri "https://quantaroute.co.uk/api/optimise-route" `
  -ContentType "application/json" `
  -Headers $headers `
  -Body $body
```

Unblock yourself as owner right now (durable fix, requires deploy + env var):

```text
1. In Render, set ADMIN_KEY to a long random secret on the quantaroute web service.
2. Redeploy.
3. Visit https://quantaroute.co.uk/?admin_key=<the ADMIN_KEY value> once from your browser.
4. Your browser now bypasses the free-trial/paywall gate for a year via a signed cookie.
```

Unblock yourself as owner right now (immediate stopgap, no deploy needed if already deployed):

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
$env:DATABASE_URL="postgresql://user:password@host:5432/database"
python scripts\mark_paying.py --identifier <your current public IP>
$env:DATABASE_URL=$null
```

MCP install/build/run:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute\mcp
npm install
npm run build
$env:QUANTAROUTE_API_BASE_URL="https://quantaroute.co.uk"
$env:QUANTAROUTE_API_KEY="optional-during-public-testing"
npm start
```

MCP tests:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute\mcp
npm run test:api-call
npm run test:mcp-call
```

Python tests:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
python -m pip install -r requirements-dev.txt
python -m pytest -q
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
- It is created automatically on startup by `backend/database.py` when `DATABASE_URL` is not set.
- Tables: `quantaroute_route_history`, `quantaroute_api_keys`, and `quantaroute_usage_events`.

Postgres production database:

- Set `DATABASE_URL` in the Render web service environment.
- The same namespaced QuantaRoute tables are created automatically on startup.
- Route sheets at `/route-sheet/{route_id}` use Postgres records when `DATABASE_URL` is configured, so links can survive redeploys.
