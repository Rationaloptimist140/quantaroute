# QuantaRoute

Turn delivery stops into a driver-ready Google Maps route in seconds.

QuantaRoute helps UK couriers and small delivery operators reduce wasted miles by optimising stop order, estimating fuel savings, and creating WhatsApp-ready Google Maps links. No app install needed. **QuantaRoute is free to use, for everyone, with no account or payment required.**

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

## CSV Upload Formats

Uploading a CSV in the web app sends the file to `POST /quantum/upload-csv`,
which parses and optimises it in one step. Three formats are supported, in
this detection order:

**1. Recommended standard: `Postcode,Number`** (detected from the header row)

```csv
Postcode,Number
WC1X 0GB,1
SE1 9JE,3
```

- `Postcode` becomes the delivery address.
- `Number` is a stop count/weight for that stop (currently captured and
  validated, not yet used by the routing algorithm itself). Blank or
  non-numeric values default to `1`.

**2. Headerless compatibility format: `WC1X 0GB,1`** (no header row)

```csv
WC1X 0GB,1
EC3M 1EB,20
EC2A 2EG,12
```

- Detected when there's no recognised header row and every non-empty row
  has exactly two columns.
- Column 1 is taken directly as the address/postcode, column 2 as the stop
  count/weight (same defaulting rule as above).
- This exists specifically so a bare postcode with nothing else on the line
  is treated as a real address, rather than being discarded by the more
  cautious legacy parser below.

**3. Rich property format: `Property Name,Address,Postcode,Type`** (detected
from the header row)

```csv
Property Name,Address,Postcode,Type
Old School Building,1 Naoroji Street Clerkenwell,WC1X 0GB,Office
Riverside House,22 Bankside,SE1 9JE,Retail
```

- `Property Name` and `Type` are ignored for routing.
- The delivery address is built from `Address` + `Postcode`.

All three are normalised internally into the same shape (`address`,
`stop_count`) before routing. If a CSV matches none of the three — its
header doesn't match either standard format, and its rows aren't a clean
two-column shape — QuantaRoute falls back to its original, more flexible
legacy parser (a loosely-shaped multi-column export, or any other
addresses-with-no-fixed-column-count file) — existing older CSVs keep
working. A clear error is only shown if the file can't be read via any of
the three formats or the legacy fallback — the message names which formats
are accepted and, where possible, what specifically was wrong (empty file,
no recognisable stops, or only one stop found when at least two are
needed).

The web app's upload section has **"Download postcode template"** and
**"Download property template"** buttons that download ready-made example
files for each format directly (served from `frontend/assets/`). The same
content also lives in `examples/csv-format-postcode-number.csv` and
`examples/csv-format-property.csv` for repo/documentation reference.

On successful upload, the app also shows a subtle note confirming which
format was detected (e.g. "uploaded (Postcode,Number format detected)").

## Public API

POST `/api/optimise-route`

Optional:

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
monthly limit return structured `429` JSON. Requests without a key work the
same way — the API is free either way.

## API Keys

API keys are entirely optional. They give partners and developers a dedicated
monthly request allowance when integrating with the public API — they are
**not** a payment or billing mechanism; QuantaRoute has no billing system at
all. Raw keys are not stored; the backend stores a SHA-256 hash.

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

## Endpoint Responsibilities

- `GET /health` — lightweight liveness check, fast, no external dependency probes.
- `GET /api/status` — richer readiness view: checks the database, postcodes.io, Nominatim, and OSRM, and reports which env vars are configured.
- `GET /api/usage-status` — simple access confirmation for the frontend. Always returns full access; there is no billing/trial state to report.

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
- QuantaRoute is free to use. There is no payment provider, checkout, or billing system anywhere in this codebase.

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
        "QUANTAROUTE_API_KEY": "optional"
      }
    }
  }
}
```

## Pricing

QuantaRoute is free. There is no subscription, no per-route fee, and no card
required. See `/pricing` for the current pricing page.

## Safety

QuantaRoute provides estimated route optimisation and fuel-saving calculations. It does not guarantee the mathematically shortest route in all cases. Drivers must follow road laws, live traffic conditions, vehicle restrictions, and professional judgement.

## Stack

- Backend: Python + FastAPI
- Production storage: Postgres via `DATABASE_URL`, SQLite fallback locally
- Frontend: HTML/CSS/JavaScript
- Routing data: public geocoding and OSRM road-network distances
- Deployment: Render

QuantaRoute has no billing/payment integration. It previously had a Stripe-based
monthly plan; this was permanently removed on 2026-07-30 so the product is free
for everyone. See `PROJECT_NOTES.md` for history.

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
