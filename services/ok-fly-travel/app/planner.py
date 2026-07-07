from __future__ import annotations

import datetime as dt

from .models import TripRequest


class Planner:
    def normalize(self, req: TripRequest) -> TripRequest:
        return TripRequest(
            origin=req.origin.upper(),
            destination=req.destination.strip(),
            start_date=req.start_date,
            end_date=req.end_date,
            travelers=max(1, int(req.travelers)),
            budget_usd=max(0.0, float(req.budget_usd)),
            preferences=[p.strip().lower() for p in req.preferences if p.strip()],
            pace=req.pace,
            trip_type=req.trip_type,
        )

    def infer_city_code(self, destination: str) -> str:
        key = destination.lower()
        mapping = {
            "tokyo": "TYO", "singapore": "SIN", "hong kong": "HKG",
            "bangkok": "BKK", "seoul": "SEL", "dubai": "DXB",
            "paris": "PAR", "london": "LON", "new york": "NYC",
        }
        for k, v in mapping.items():
            if k in key or key in k:
                return v
        return "TYO"

    def trip_days(self, req: TripRequest) -> int:
        s = dt.date.fromisoformat(req.start_date)
        e = dt.date.fromisoformat(req.end_date)
        return max(1, (e - s).days + 1)
