# QuantaRoute

Turn delivery stops into a driver-ready Google Maps route in seconds.

QuantaRoute helps UK couriers and small delivery operators reduce wasted miles by optimising stop order, estimating fuel savings, and creating WhatsApp-ready Google Maps links. No app install needed.

## Live Product

- App: https://quantaroute.co.uk
- Landing page: https://quantaroute.co.uk/landing.html
- Pricing: https://quantaroute.co.uk/pricing
- API docs: https://quantaroute.co.uk/openapi.json
- LLM guide: https://quantaroute.co.uk/llms.txt

## Key Features

- Real road-network distances rather than straight-line estimates
- Smart stop reordering for small multi-drop routes
- Estimated fuel saving and distance saving against the entered order
- Optional start/depot address and return-to-start support
- Google Maps route link
- WhatsApp-ready driver message/link
- Printable browser route sheet
- Persistent route history with Postgres in production
- CSV upload or pasted stops
- Mobile-friendly browser app

## Public API

POST `/api/optimise-route`

Optional during public testing:

```text
X-API-Key: qr_your_key_here
```

```json
{
  "start": "Plymouth, UK",
  "stops": [
    "Drake Circus Shopping Centre, Plymouth",
    "Royal William Yard, Plymouth",
    "Plymouth Market, Plymouth",
    "Plymouth Railway Station, Plymouth"
  ],
  "end": "Plymouth, UK",
  "vehicle": "van",
  "optimise_for": "distance"
}
```

The endpoint returns ordered stops, original and optimised distance estimates, distance saved, estimated saving percentage, a Google Maps URL, a WhatsApp driver message, printable route sheet URL, optional API-client metadata, and warnings.

When a valid API key is supplied, the response includes an `api_client` object
with `label`, `usage_count_current_month`, and `monthly_limit`. Invalid or
inactive keys are rejected with structured `401` JSON. Keys that exceed their
monthly limit return structured `429` JSON. Requests without a key still work
during public testing.

## API Keys

API keys are optional while QuantaRoute is free to test. They are being prepared
for future paid API access, rate limits, and per-route billing. Raw keys are not
stored; the backend stores a SHA-256 hash.

Important: `scripts/create_api_key.py` writes to whichever storage backend the
script can see. If you run it locally without `DATABASE_URL`, it creates the key
in local SQLite at `backend/quantaroute.db`. That local key will not exist in
live Render Postgres and will not work against production.

Create a local/dev SQLite key:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
python scripts\create_api_key.py --label "Courier Bot" --monthly-limit 1000 --source-label courier_bot
```

### Create a Production API Key

Method 1: run the local script with production `DATABASE_URL` set.

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
$env:DATABASE_URL="postgresql://user:password@host:5432/database"
python scripts\create_api_key.py --label "Rana test key" --monthly-limit 100
$env:DATABASE_URL=$null
```

Use the Render Postgres connection string for `DATABASE_URL`. Do not commit it,
paste it into docs, or share it in screenshots.

Method 2: use a Render shell if available.

Open a shell for the QuantaRoute Render web service, confirm the service has
`DATABASE_URL` configured, then run one of these depending on the shell's
working directory:

```bash
# If the shell starts at the repository root:
python scripts/create_api_key.py --label "Rana test key" --monthly-limit 100

# If the shell starts in the backend rootDir:
python ../scripts/create_api_key.py --label "Rana test key" --monthly-limit 100
```

The script prints the raw key once. Store it securely immediately.

Example API call with a key:

```powershell
$headers = @{ "X-API-Key" = "qr_your_key_here" }
$body = @{
  start = "Plymouth Railway Station, North Road, Plymouth, PL4 6AB"
  stops = @(
    "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
    "Royal William Yard, Plymouth, PL1 3RP"
  )
  end = "Plymouth Railway Station, North Road, Plymouth, PL4 6AB"
  vehicle = "van"
  optimise_for = "distance"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "https://quantaroute.co.uk/api/optimise-route" `
  -ContentType "application/json" `
  -Headers $headers `
  -Body $body
```

The raw key is shown once by the creation script. QuantaRoute stores only a
SHA-256 hash, plus safe metadata such as label, monthly limit, current month
usage count, and notes.

## Admin / Owner Bypass

The free-trial gate blocks any visitor identifier (IP address) 30 days after
its first use — including the site owner's own IP if it was used for early
testing. There is now a durable override, configured entirely via Render
environment variables (no code changes or manual DB edits needed after the
first setup):

- `ADMIN_KEY` — a shared secret. Visit any URL once with `?admin_key=<value>`
  (for example `https://quantaroute.co.uk/?admin_key=your-secret`) and the
  browser receives a signed, `httponly` cookie valid for a year that bypasses
  the free-trial/paywall gate on every later request from that browser. The
  same value can be sent as an `X-Admin-Key` header instead, for
  scripts/curl/Postman rather than a browser.
- `ADMIN_BYPASS_IPS` — optional comma-separated list of IP addresses that
  always bypass the gate with no key needed. Useful as a fallback for a known
  static office IP, but `ADMIN_KEY` is the primary mechanism since consumer
  IPs change.

Set `ADMIN_KEY` in the Render service environment to a long random value and
keep it private — anyone with the value gets unlimited free routes.

If you need to unblock a specific already-recorded identifier right now
without waiting for a deploy, `scripts/mark_paying.py` flips that identifier's
`is_paying` flag directly (see script docstring for usage). This is a
one-time stopgap; `ADMIN_KEY`/`ADMIN_BYPASS_IPS` is the lasting fix.

## Agent-Ready Direction

QuantaRoute is being developed as an API and MCP-compatible tool for AI assistants and business agents.

Example agent task:

> Here are 18 delivery addresses. Optimise the route, estimate distance and fuel saving, create a Google Maps link, and prepare a WhatsApp message for the driver.

MCP preparation lives in `mcp/server.ts` with the `optimise_delivery_route` tool schema.

## QuantaRoute Agent/API Surface

- Web app: https://quantaroute.co.uk
- Developer page: https://quantaroute.co.uk/developers.html
- Public API: `POST /api/optimise-route`
- Printable route sheet: `/route-sheet/{route_id}`
- OpenAPI JSON: https://quantaroute.co.uk/openapi.json
- LLM guide: https://quantaroute.co.uk/llms.txt
- MCP tool: `optimise_delivery_route`
- Optional API key header: `X-API-Key`

## Route History Storage

QuantaRoute uses `DATABASE_URL` when it is present. Set this to a Postgres
connection string in production so route history and `/route-sheet/{route_id}`
links survive Render restarts and redeploys.

If `DATABASE_URL` is missing, the backend falls back to local SQLite at
`backend/quantaroute.db`. This is useful for development, but SQLite files on
Render's free-tier filesystem can disappear after restarts or redeploys.

Render setup:

1. Create a Render Postgres database.
2. Copy its internal database URL.
3. Add it to the QuantaRoute web service environment as `DATABASE_URL`.
4. Redeploy the web service. The backend creates the required tables on startup.

## Route History Export

Export route history before changing storage, rotating databases, or letting a
free Render Postgres instance expire. The export script uses Postgres when
`DATABASE_URL` is set and local SQLite otherwise.

Local SQLite export:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
python scripts\export_route_history.py --output-dir exports --format both --base-url https://quantaroute.co.uk
```

Postgres export from any shell with the production database URL:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
$env:DATABASE_URL="postgresql://user:password@host:5432/database"
python scripts\export_route_history.py --output-dir exports --format both --base-url https://quantaroute.co.uk
```

Render one-off shell/export:

```powershell
python scripts\export_route_history.py --output-dir exports --format both --base-url https://quantaroute.co.uk
```

The script writes timestamped JSON and CSV files named like
`quantaroute_route_history_YYYYMMDD_HHMMSS.json` and `.csv`. CSV list fields
such as `original_stops` and `ordered_stops` are JSON-encoded inside the cell so
commas inside addresses remain safe. `route_sheet_url` is built from
`--base-url`, so set that to the live domain or local server you want in the
backup.

Safety notes:

- Distance and fuel savings are estimates.
- QuantaRoute does not guarantee the mathematically shortest route in all cases.
- Drivers must follow road laws, live traffic conditions, vehicle restrictions, and professional judgement.
- Stripe checkout for the monthly plan is being wired up; pay-per-route checkout is not yet automated either. Public testing remains free while payments are prepared.
- API keys are optional during public testing and will become part of paid/API access later.

Local API test:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute\backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

MCP local test:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute\mcp
npm install
npm run build
$env:QUANTAROUTE_API_BASE_URL="http://127.0.0.1:8000"
npm run test:mcp-call
```

## MCP Server

Install and build:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute\mcp
npm install
npm run build
```

Run the stdio MCP server:

```powershell
$env:QUANTAROUTE_API_BASE_URL="https://quantaroute.co.uk"
npm start
```

For local backend testing:

```powershell
$env:QUANTAROUTE_API_BASE_URL="http://127.0.0.1:8000"
npm start
```

MCP config example:

```json
{
  "mcpServers": {
    "quantaroute": {
      "command": "node",
      "args": [
        "C:\\Users\\rw718\\Desktop\\QuantaRoute\\mcp\\dist\\server.js"
      ],
      "env": {
        "QUANTAROUTE_API_BASE_URL": "https://quantaroute.co.uk",
        "QUANTAROUTE_API_KEY": "optional-during-public-testing"
      }
    }
  }
}
```

## Pricing

First month free for testing. Then £1.99 per optimised route, or a monthly
plan at £1.99/month for up to 100 routes for regular couriers. No forced
subscription on the pay-per-route tier; payments are currently being
prepared/wired up for both. See `/pricing` for the current pricing page.

## Safety

QuantaRoute provides estimated route optimisation and fuel-saving calculations. It does not guarantee the mathematically shortest route in all cases. Drivers must follow road laws, live traffic conditions, vehicle restrictions, and professional judgement.

## Stack

- Backend: Python + FastAPI
- Production storage: Postgres via `DATABASE_URL`, SQLite fallback locally
- Frontend: HTML/CSS/JavaScript
- Routing data: public geocoding and OSRM road-network distances
- Payments: Stripe (monthly plan integration in progress)
- Deployment: Render

## Development

```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then visit `http://localhost:8000`.

## Tests

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

MCP checks:

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute\mcp
npm run build
npm run test:api-call
npm run test:mcp-call
```
