from __future__ import annotations

import datetime as dt
import re

from .models import TripRequest


# Known city → IATA metro code. This is intentionally a *convenience* map, not the
# source of truth: any city not listed is resolved by geocoding (see service.py),
# NOT silently coerced to a default city.
CITY_CODE_MAP = {
    "tokyo": "TYO", "singapore": "SIN", "hong kong": "HKG", "bangkok": "BKK",
    "seoul": "SEL", "dubai": "DXB", "paris": "PAR", "london": "LON",
    "new york": "NYC", "taipei": "TPE", "new taipei": "TPE", "tainan": "TNN",
    "台南": "TNN", "台北": "TPE", "高雄": "KHH", "kaohsiung": "KHH",
    "taichung": "RMQ", "台中": "RMQ", "osaka": "OSA", "大阪": "OSA",
    "kyoto": "UKY", "京都": "UKY", "東京": "TYO", "东京": "TYO",
    "首爾": "SEL", "首尔": "SEL", "曼谷": "BKK", "新加坡": "SIN", "香港": "HKG",
}


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
        """Best-effort metro code. NEVER silently returns a real city for an
        unknown destination (the old behaviour was to return "TYO", which made a
        Tainan request come back as Tokyo). For an unknown city we return a
        deterministic placeholder code derived from the name so it is clearly
        distinct — the real display name comes from geocoding, not this code."""
        key = destination.strip().lower()
        for k, v in CITY_CODE_MAP.items():
            if k in key or key in k:
                return v
        alpha = re.sub(r"[^a-z]", "", key)
        return alpha[:3].upper() if len(alpha) >= 3 else "UNK"

    def is_known_city(self, destination: str) -> bool:
        key = destination.strip().lower()
        return any(k in key or key in k for k in CITY_CODE_MAP)

    def trip_days(self, req: TripRequest) -> int:
        s = dt.date.fromisoformat(req.start_date)
        e = dt.date.fromisoformat(req.end_date)
        return max(1, (e - s).days + 1)
