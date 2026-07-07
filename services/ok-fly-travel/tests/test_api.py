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
