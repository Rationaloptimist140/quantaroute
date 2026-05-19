# QuantaRoute 🚗

**Smart route optimization for UK couriers and delivery drivers.** Paste or upload your stops, get back an optimized delivery order that saves fuel.

No app download. No account required. No subscription lock-in.

## Quick Start

1. Go to **[quantaroute.onrender.com](https://quantaroute.onrender.com)**
2. Enter your stops (postcode, address, or business name)
3. Optionally set a start/depot address
4. Get your optimized route + fuel savings + Google Maps link

## Key Features

- ✅ Real road-network distances (not straight-line estimates)
- ✅ Quantum-assisted optimization for 8-20 stops
- ✅ CSV upload or paste individual stops
- ✅ Mobile-friendly
- ✅ Built for UK postcodes
- ✅ Free first month, then £1.99 per route

## How It Works

QuantaRoute uses:
- **Qiskit QAOA** quantum simulation for 8-20 stop routes
- **Exact brute-force** optimization for smaller routes
- **Nearest-neighbour** for larger routes
- Real **OSRM road distances** (not crow-flies estimates)

## Proven Results

- 5 stops (Plymouth/Exeter): **3.74% fuel saved**
- 30 stops (South West England): **13.62% fuel saved**

## Pricing

- **Free**: First month of unlimited routes
- **Paid**: £1.99 per optimized route after trial ends

## Stack

- **Backend**: Python + FastAPI + Qiskit
- **Frontend**: HTML/CSS/JavaScript (mobile-first)
- **Database**: SQLite (route history + usage tracking)
- **Deployment**: Render

## API

POST `/quantum/route-optimise`

```json
{
  "addresses": ["SW1A 1AA", "EC1A 1BB", "W1A 0AX"],
  "driver_name": "Driver",
  "start_address": "EC4M 8RT",
  "return_to_start": true
}
```

See `PROJECT_NOTES.md` for full details.

## Development

```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then visit `http://localhost:8000`

---

**Ready to optimize?** → [Launch App](https://quantaroute.onrender.com)
