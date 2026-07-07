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
            "properties": {
                "origin":      {"type": "string", "examples": ["HKG"]},
                "destination": {"type": "string", "examples": ["Tokyo"]},
                "start_date":  {"type": "string", "format": "date"},
                "end_date":    {"type": "string", "format": "date"},
                "travelers":   {"type": "integer", "minimum": 1, "default": 1},
                "budget_usd":  {"type": "number", "minimum": 0, "default": 0},
                "preferences": {"type": "array", "items": {"type": "string"}, "default": []},
                "pace":        {"type": "string", "enum": ["relaxed","balanced","packed"], "default": "balanced"},
                "trip_type":   {"type": "string", "enum": ["leisure","business","family","honeymoon","solo"], "default": "leisure"},
            },
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
        "notes": [
            "Flights and hotels are deterministic mock data for demo reliability.",
            "POI and weather fetched from free public sources (Overpass, Open-Meteo).",
            "Crypto-friendly labels are advisory heuristics, not booking guarantees.",
        ],
    }
