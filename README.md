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

The endpoint returns ordered stops, original and optimised distance estimates, distance saved, estimated saving percentage, a Google Maps URL, a WhatsApp driver message, and warnings.

## Agent-Ready Direction

QuantaRoute is being developed as an API and MCP-compatible tool for AI assistants and business agents.

Example agent task:

> Here are 18 delivery addresses. Optimise the route, estimate distance and fuel saving, create a Google Maps link, and prepare a WhatsApp message for the driver.

MCP preparation lives in `mcp/server.ts` with the `optimise_delivery_route` tool schema.

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
