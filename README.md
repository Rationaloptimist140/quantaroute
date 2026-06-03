# QuantaRoute

Turn delivery stops into a driver-ready Google Maps route in seconds.

QuantaRoute helps UK couriers and small delivery operators reduce wasted miles by optimising stop order, estimating fuel savings, and creating WhatsApp-ready Google Maps links. No app install needed.

## Live Product

- App: https://quantaroute.co.uk
- Landing page: https://quantaroute.co.uk/landing.html
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
- CSV upload or pasted stops
- Mobile-friendly browser app

## Public API

POST `/api/optimise-route`

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

The endpoint returns ordered stops, original and optimised distance estimates, distance saved, estimated saving percentage, a Google Maps URL, a WhatsApp driver message, printable route sheet URL, and warnings.

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

Safety notes:

- Distance and fuel savings are estimates.
- QuantaRoute does not guarantee the mathematically shortest route in all cases.
- Drivers must follow road laws, live traffic conditions, vehicle restrictions, and professional judgement.
- Stripe checkout is not active yet; public testing remains free while payments are prepared.

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
        "QUANTAROUTE_API_BASE_URL": "https://quantaroute.co.uk"
      }
    }
  }
}
```

## Pricing

First month free for testing. Then £1.99 per optimised route. No subscription, no monthly fee, and payments are currently being prepared.

## Safety

QuantaRoute provides estimated route optimisation and fuel-saving calculations. It does not guarantee the mathematically shortest route in all cases. Drivers must follow road laws, live traffic conditions, vehicle restrictions, and professional judgement.

## Stack

- Backend: Python + FastAPI + SQLite
- Frontend: HTML/CSS/JavaScript
- Routing data: public geocoding and OSRM road-network distances
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
