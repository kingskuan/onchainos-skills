from __future__ import annotations

from typing import Any, Dict


def get_a2a_service_contract() -> Dict[str, Any]:
    return {
        "service_name": "travel-planner-asp",
        "display_name": "Crypto-Friendly Travel Planner",
        "version": "0.1.0",
        "description": (
            "An agentic travel planning service for OKX.AI. "
            "Turns trip inputs into structured itineraries, budget breakdowns, "
            "POI-backed recommendations, and crypto-friendly destination notes."
        ),
        "mode": "a2a",
        "capabilities": [
            "trip_intake", "multi_step_research", "itinerary_optimization",
            "budget_projection", "crypto_friendly_annotation", "structured_report_generation",
        ],
        "input_schema": {
            "type": "object",
            "required": ["origin", "destination", "start_date", "end_date"],
            "additionalProperties": True,
            "properties": {
                "origin":      {"type": "string", "examples": ["HKG"], "aliases": ["from", "departure"]},
                "destination": {"type": "string", "examples": ["Tokyo", "Tainan"], "aliases": ["to", "dest"]},
                "start_date":  {"type": "string", "format": "date", "aliases": ["startDate", "check_in", "checkIn"]},
                "end_date":    {"type": "string", "format": "date", "aliases": ["endDate", "check_out", "checkOut"]},
                "travelers":   {"type": "integer", "minimum": 1, "default": 1, "aliases": ["adults", "pax"]},
                "budget_usd":  {"type": "number", "minimum": 0, "default": 0, "aliases": ["budgetUsd", "budget"]},
                "preferences": {"type": "array", "items": {"type": "string"}, "default": []},
                "pace":        {"type": "string", "enum": ["relaxed","balanced","packed"], "default": "balanced"},
                "trip_type":   {"type": "string", "enum": ["leisure","business","family","honeymoon","solo"], "default": "leisure", "aliases": ["tripType"]},
            },
            "x-field-naming": (
                "Both snake_case (start_date) and camelCase (startDate) are accepted for "
                "every field, plus the listed aliases. Unknown extra keys are ignored, so a "
                "minor field-name mismatch will NOT fail a paid request."
            ),
        },
        "output_schema": {
            "type": "object",
            "required": ["request", "research", "json", "markdown", "best_plan"],
            "properties": {
                "request":   {"type": "object"},
                "research":  {"type": "object"},
                "json":      {"type": "object"},
                "markdown":  {"type": "string"},
                "best_plan": {"type": ["object", "null"]},
            },
        },
        "transport": {
            "protocol": "http",
            "methods": {
                "manifest": {"method": "GET",  "path": "/a2a/manifest"},
                "invoke":   {"method": "POST", "path": "/a2a/invoke"},
                "health":   {"method": "GET",  "path": "/health"},
            },
        },
        "data_mode": "simulated_flights_hotels+live_poi_weather",
        "notes": [
            "Flight & hotel prices are SIMULATED planning estimates (deterministic, "
            "no live booking API) — not bookable fares. The response carries a "
            "`disclaimer` and per-plan assumptions saying so.",
            "POI and weather are fetched LIVE from free public sources (OSM Nominatim/"
            "Overpass, Open-Meteo) for the geocoded destination.",
            "The destination is resolved by geocoding; if it cannot be resolved the "
            "service says so and omits POIs/weather rather than substituting another city.",
            "Crypto-friendly labels are advisory heuristics, not booking guarantees.",
        ],
    }
