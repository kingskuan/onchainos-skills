from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.models import FlightOption, HotelOption, POIOption

client = TestClient(app)


def _patch_demo_sources():
    main_module.service.amadeus.search_flights = lambda **kwargs: [
        FlightOption(
            provider="MockAir", departure="2026-08-12T08:10", arrival="2026-08-12T12:25",
            duration_minutes=255, price_usd=218.0, currency="USD",
            itinerary_id="MOCK-FLT-1", raw={"generated": True},
        )
    ]
    main_module.service.amadeus.search_hotels = lambda **kwargs: [
        HotelOption(
            provider="MockStay", name="Tokyo Boutique Hotel", city_code="TYO",
            price_usd_per_night=165.0, score=4.5, address="Shibuya area, Tokyo",
            raw={"generated": True},
        )
    ]
    main_module.service.otm.search_pois = lambda *args, **kwargs: [
        POIOption(name="Senso-ji", kind="historic", rating=4.8, distance_km=2.1,
                  url="https://www.openstreetmap.org/node/1", raw={"generated": True}),
        POIOption(name="Shibuya Crossing", kind="attraction", rating=4.9, distance_km=1.2,
                  url="https://www.openstreetmap.org/node/2", raw={"generated": True}),
    ]
    main_module.service.otm.get_weather = lambda *args, **kwargs: {
        "location": "Tokyo, Japan", "latitude": 35.6762, "longitude": 139.6503,
        "daily": {"time": ["2026-08-12"], "temperature_2m_max": [31.0], "temperature_2m_min": [25.0]},
    }


SAMPLE_PAYLOAD = {
    "origin": "HKG", "destination": "Tokyo",
    "start_date": "2026-08-12", "end_date": "2026-08-16",
    "travelers": 2, "budget_usd": 2500,
    "preferences": ["food", "museums", "night view"],
    "pace": "balanced", "trip_type": "leisure",
}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_a2a_manifest():
    resp = client.get("/a2a/manifest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_name"] == "travel-planner-asp"
    assert "input_schema" in data


def test_plan_shape():
    _patch_demo_sources()
    resp = client.post("/plan", json=SAMPLE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["request"]["origin"] == "HKG"
    assert data["research"]["city_code"] == "TYO"
    assert data["research"]["flight_count"] >= 1
    assert data["research"]["hotel_count"] >= 1
    assert "plans" in data["json"]
    assert len(data["json"]["plans"]) >= 1
    assert "Option 1" in data["markdown"]
    assert data["best_plan"] is not None
    assert "crypto_friendly_notes" in data["best_plan"]


def test_a2a_invoke():
    _patch_demo_sources()
    resp = client.post("/a2a/invoke", json=SAMPLE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert "best_plan" in data
    assert "markdown" in data


def test_weather_and_demo_layer():
    _patch_demo_sources()
    resp = client.post("/plan", json={**SAMPLE_PAYLOAD, "pace": "relaxed"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["research"]["weather"]["location"] == "Tokyo, Japan"
    assert "crypto_friendly" in data["research"]["city_demo"]


def test_camelcase_field_names_accepted():
    """Regression: a buyer sending camelCase (startDate/endDate/budget) must NOT
    422 — that mismatch previously happened AFTER x402 settled, double-charging."""
    _patch_demo_sources()
    resp = client.post("/plan", json={
        "origin": "HKG", "destination": "Tokyo",
        "startDate": "2026-08-12", "endDate": "2026-08-16",
        "adults": 2, "budget": 2500, "tripType": "leisure",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["request"]["start_date"] == "2026-08-12"
    assert data["request"]["end_date"] == "2026-08-16"
    assert data["request"]["travelers"] == 2


def test_unknown_destination_is_not_silently_tokyo():
    """Regression: an unlisted destination must resolve to ITSELF, never fall back
    to Tokyo for flights/hotels (the reported Tainan→Tokyo bug)."""
    # Restore the real (deterministic, offline) flight/hotel provider — earlier
    # tests monkeypatch it to a hardcoded Tokyo hotel on the shared service.
    from app.clients import AmadeusClient
    main_module.service.amadeus = AmadeusClient()
    # Use the built-in offline fallback for Tainan; skip live POI/weather calls.
    main_module.service.otm.search_pois = lambda *a, **k: []
    main_module.service.otm.get_weather = lambda *a, **k: None
    resp = client.post("/plan", json={
        "origin": "HKG", "destination": "台南",
        "start_date": "2026-07-24", "end_date": "2026-07-27",
        "travelers": 4, "budget_usd": 2000, "pace": "relaxed",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["research"]["city_code"] == "TNN"
    assert "Tainan" in data["research"]["resolved_destination"]
    hotel_name = (data["best_plan"]["hotel"] or {}).get("name", "")
    assert "tokyo" not in hotel_name.lower()
    assert data["data_mode"].startswith("simulated")
