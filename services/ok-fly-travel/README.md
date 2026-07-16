# Crypto-Friendly Travel Planner ASP

A lightweight travel planning agent service for OKX.AI / Onchain OS.

Generates structured itineraries, budget breakdowns, POI-backed daily plans, and crypto-friendly destination notes.

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check:
```bash
curl http://127.0.0.1:8000/health
```

Plan a trip:
```bash
curl -X POST http://127.0.0.1:8000/plan \
  -H 'Content-Type: application/json' \
  -d '{
    "origin":"HKG",
    "destination":"Tokyo",
    "start_date":"2026-08-12",
    "end_date":"2026-08-16",
    "travelers":2,
    "budget_usd":2500,
    "preferences":["food","museums","night view"],
    "pace":"balanced",
    "trip_type":"leisure"
  }'
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /plan | Plan a trip (debug) |
| GET | /a2a/manifest | A2A service manifest |
| POST | /a2a/invoke | A2A invocation endpoint |

## Deployment (Railway)

1. Push this repo to GitHub
2. Connect the repo in [railway.app](https://railway.app)
3. Railway auto-detects the `Dockerfile` and `railway.toml`
4. Done — grab the public URL for ASP registration

## Environment Variables (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| OSM_USER_AGENT | travel-agent-mvp/0.1 | UA for OSM requests |
| NOMINATIM_URL | https://nominatim.openstreetmap.org/search | Geocoding |
| OVERPASS_URL | https://overpass-api.de/api/interpreter | POI data |
| OPEN_METEO_URL | https://api.open-meteo.com/v1/forecast | Weather |

## Data Sources

- **POI**: Overpass API (OpenStreetMap) — free, no key needed
- **Geocoding**: Nominatim — free, no key needed
- **Weather**: Open-Meteo — free, no key needed
- **Flights/Hotels**: Deterministic mock data (demo reliability)

## Notes

- Flight and hotel data are mocked for demo stability.
- Crypto-friendly labels are advisory heuristics, not booking guarantees.
- POI fallback to static demo data if Overpass is rate-limited.
