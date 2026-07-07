from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import random
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .demo_data import city_demo_by_name
from .models import FlightOption, HotelOption, POIOption


def http_json(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Any:
    data = None
    hdrs = headers.copy() if headers else {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text.strip() else {}


def _ua() -> str:
    return os.getenv("OSM_USER_AGENT", "travel-agent-mvp/0.1 (demo)")


def _seed(*parts: str) -> int:
    raw = "||".join(parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


CITY_PROFILE_BY_CODE: Dict[str, Dict[str, Any]] = {
    "TYO": {"name": "Tokyo",     "region": "apac",   "flight_base": 220, "hotel_base": 160, "flight_hours": (2, 7)},
    "SIN": {"name": "Singapore", "region": "apac",   "flight_base": 180, "hotel_base": 200, "flight_hours": (2, 6)},
    "HKG": {"name": "Hong Kong", "region": "apac",   "flight_base": 160, "hotel_base": 150, "flight_hours": (1, 5)},
    "BKK": {"name": "Bangkok",   "region": "apac",   "flight_base": 140, "hotel_base":  90, "flight_hours": (2, 6)},
    "SEL": {"name": "Seoul",     "region": "apac",   "flight_base": 200, "hotel_base": 140, "flight_hours": (2, 6)},
    "DXB": {"name": "Dubai",     "region": "mea",    "flight_base": 420, "hotel_base": 240, "flight_hours": (6, 12)},
    "PAR": {"name": "Paris",     "region": "europe", "flight_base": 520, "hotel_base": 260, "flight_hours": (11, 15)},
    "LON": {"name": "London",    "region": "europe", "flight_base": 540, "hotel_base": 280, "flight_hours": (11, 15)},
    "NYC": {"name": "New York",  "region": "na",     "flight_base": 680, "hotel_base": 320, "flight_hours": (14, 18)},
}

FLIGHT_DEPARTURE_TIMES = ["08:10", "13:40", "22:15"]
HOTEL_ZONES = ["Central", "Transit Core", "Lifestyle District", "Quiet Residential", "Riverfront"]

# Coarse pricing bands by region, used when a destination is NOT in the known-city
# table. This lets us estimate for any geocoded city without falling back to a
# specific wrong city's profile (the old bug: unknown city inherited Tokyo).
REGION_BASE = {
    "apac":   {"flight_base": 200, "hotel_base": 150, "flight_hours": (2, 7)},
    "mea":    {"flight_base": 420, "hotel_base": 240, "flight_hours": (6, 12)},
    "europe": {"flight_base": 520, "hotel_base": 260, "flight_hours": (10, 15)},
    "na":     {"flight_base": 640, "hotel_base": 300, "flight_hours": (12, 18)},
    "global": {"flight_base": 300, "hotel_base": 160, "flight_hours": (3, 10)},
}


def region_from_latlon(lat: Optional[float], lon: Optional[float]) -> str:
    """Coarse continent bucket from coordinates — only used for pricing bands."""
    if lat is None or lon is None:
        return "global"
    if -50 <= lat <= 60 and 60 <= lon <= 180:
        return "apac"
    if 10 <= lat <= 45 and 25 <= lon <= 63:
        return "mea"
    if 34 <= lat <= 72 and -25 <= lon <= 45:
        return "europe"
    if 5 <= lat <= 72 and -168 <= lon <= -52:
        return "na"
    return "global"


def build_city_profile(city_code: str, display_name: Optional[str] = None,
                       region: Optional[str] = None) -> Dict[str, Any]:
    """Profile for flights/hotels. Known codes use their curated profile; unknown
    destinations use a region-based band and ALWAYS carry the real display name so
    a Tainan trip is never labelled 'Tokyo'."""
    known = CITY_PROFILE_BY_CODE.get(city_code.upper())
    if known:
        prof = dict(known)
        if display_name:
            prof["name"] = display_name
        return prof
    band = REGION_BASE.get(region or "global", REGION_BASE["global"])
    return {
        "name": display_name or city_code.upper(),
        "region": region or "global",
        **band,
    }


class AmadeusClient:
    """Deterministic mock provider for flights + hotels. No API key required."""

    def search_flights(
        self,
        origin: str,
        destination: str,
        start_date: str,
        adults: int = 1,
        currency: str = "USD",
        max_results: int = 5,
        display_name: Optional[str] = None,
        region: Optional[str] = None,
    ) -> List[FlightOption]:
        dest_profile = build_city_profile(destination, display_name, region)
        rng = random.Random(_seed(origin, destination, start_date, str(adults)))
        low_h, high_h = dest_profile["flight_hours"]
        options: List[FlightOption] = []

        for idx, dep_time in enumerate(FLIGHT_DEPARTURE_TIMES[:max_results]):
            hours = rng.randint(low_h, high_h)
            minutes = rng.choice([0, 15, 30, 45])
            duration_minutes = max(45, hours * 60 + minutes + rng.randint(-20, 35))
            base = dest_profile["flight_base"]
            price_mult = [0.84, 1.00, 1.18][min(idx, 2)]
            price = max(60.0, round((base * price_mult) + rng.randint(-25, 35), 2))
            dep_dt = dt.datetime.fromisoformat(f"{start_date}T{dep_time}:00")
            arr_dt = dep_dt + dt.timedelta(minutes=duration_minutes)

            options.append(FlightOption(
                provider="MockAir",
                departure=dep_dt.isoformat(timespec="minutes"),
                arrival=arr_dt.isoformat(timespec="minutes"),
                duration_minutes=duration_minutes,
                price_usd=price,
                currency=currency,
                itinerary_id=f"MOCK-FLT-{origin}-{destination}-{idx+1}",
                raw={"generated": True, "route_band": dest_profile["region"]},
            ))

        return options

    def search_hotels(
        self,
        city_code: str,
        check_in: str,
        check_out: str,
        adults: int = 1,
        max_results: int = 10,
        display_name: Optional[str] = None,
        region: Optional[str] = None,
    ) -> List[HotelOption]:
        profile = build_city_profile(city_code, display_name, region)
        rng = random.Random(_seed(city_code, check_in, check_out, str(adults)))
        nights = max(1, (dt.date.fromisoformat(check_out) - dt.date.fromisoformat(check_in)).days)
        base = profile["hotel_base"]

        hotel_types = [
            ("Boutique Hotel", 1.15, 4.5),
            ("Business Hotel", 1.05, 4.2),
            ("Comfort Stay", 0.90, 4.0),
            ("Lifestyle Hotel", 1.25, 4.6),
            ("Transit Hotel", 0.78, 3.8),
            ("Suite Collection", 1.45, 4.7),
            ("City Nest", 0.82, 4.1),
            ("Premium Residence", 1.55, 4.8),
        ]

        options: List[HotelOption] = []
        for idx, (label, mult, rating) in enumerate(hotel_types[:max_results]):
            zone = HOTEL_ZONES[idx % len(HOTEL_ZONES)]
            nightly = round(max(45.0, base * mult + rng.randint(-20, 40)), 2)
            score = round(min(5.0, max(3.0, rating + rng.uniform(-0.2, 0.2))), 1)
            options.append(HotelOption(
                provider="MockStay",
                name=f"{profile['name']} {label}",
                city_code=city_code,
                price_usd_per_night=nightly,
                score=score,
                address=f"{zone} area, {profile['name']}",
                raw={"generated": True, "nights": nights},
            ))

        return options


class OpenTripMapClient:
    """Uses Nominatim + Overpass (free) with static demo fallback."""

    def __init__(self) -> None:
        self.nominatim_url = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
        self.overpass_url = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
        self.open_meteo_url = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")

    def geocode(self, city_name: str) -> Optional[Dict[str, Any]]:
        params = {"format": "jsonv2", "limit": 1, "q": city_name, "addressdetails": 1}
        url = f"{self.nominatim_url}?{urllib.parse.urlencode(params)}"
        try:
            resp = http_json("GET", url, headers={"User-Agent": _ua()})
            if isinstance(resp, list) and resp:
                item = resp[0]
                return {
                    "lat": _safe_float(item.get("lat")),
                    "lon": _safe_float(item.get("lon")),
                    "display_name": item.get("display_name", city_name),
                }
        except Exception:
            pass

        # Offline fallback for when Nominatim is unreachable. If the city is not
        # here either, return None — the caller must NOT be handed another city's
        # coordinates. (The old code returned Tokyo's coords for anything unknown,
        # which is why a Tainan request produced a Tokyo itinerary.)
        fallback = {
            "tokyo":     {"lat": 35.6762, "lon": 139.6503, "display_name": "Tokyo, Japan"},
            "singapore": {"lat":  1.3521, "lon": 103.8198, "display_name": "Singapore"},
            "hong kong": {"lat": 22.3193, "lon": 114.1694, "display_name": "Hong Kong"},
            "bangkok":   {"lat": 13.7563, "lon": 100.5018, "display_name": "Bangkok, Thailand"},
            "seoul":     {"lat": 37.5665, "lon": 126.9780, "display_name": "Seoul, South Korea"},
            "dubai":     {"lat": 25.2048, "lon":  55.2708, "display_name": "Dubai, UAE"},
            "paris":     {"lat": 48.8566, "lon":   2.3522, "display_name": "Paris, France"},
            "london":    {"lat": 51.5074, "lon":  -0.1278, "display_name": "London, UK"},
            "new york":  {"lat": 40.7128, "lon": -74.0060, "display_name": "New York, USA"},
            "taipei":    {"lat": 25.0330, "lon": 121.5654, "display_name": "Taipei, Taiwan"},
            "台北":       {"lat": 25.0330, "lon": 121.5654, "display_name": "Taipei, Taiwan"},
            "tainan":    {"lat": 22.9997, "lon": 120.2270, "display_name": "Tainan, Taiwan"},
            "台南":       {"lat": 22.9997, "lon": 120.2270, "display_name": "Tainan, Taiwan"},
            "kaohsiung": {"lat": 22.6273, "lon": 120.3014, "display_name": "Kaohsiung, Taiwan"},
            "高雄":       {"lat": 22.6273, "lon": 120.3014, "display_name": "Kaohsiung, Taiwan"},
            "osaka":     {"lat": 34.6937, "lon": 135.5023, "display_name": "Osaka, Japan"},
            "大阪":       {"lat": 34.6937, "lon": 135.5023, "display_name": "Osaka, Japan"},
        }
        key = city_name.strip().lower()
        for k, v in fallback.items():
            if k in key or key in k:
                return v
        return None

    def search_pois(self, city_name: str, kinds: str = "tourism|amenity|historic|leisure", limit: int = 10) -> List[POIOption]:
        geo = self.geocode(city_name)
        if not geo:
            return []

        lat, lon = geo["lat"], geo["lon"]
        overpass_query = f"""
        [out:json][timeout:25];
        (
          node(around:5000,{lat},{lon})["tourism"];
          way(around:5000,{lat},{lon})["tourism"];
          node(around:5000,{lat},{lon})["amenity"~"restaurant|cafe|museum|theatre|arts_centre"];
          way(around:5000,{lat},{lon})["amenity"~"restaurant|cafe|museum|theatre|arts_centre"];
          node(around:5000,{lat},{lon})["historic"];
          way(around:5000,{lat},{lon})["historic"];
          node(around:5000,{lat},{lon})["leisure"~"park|garden|viewpoint"];
          way(around:5000,{lat},{lon})["leisure"~"park|garden|viewpoint"];
        );
        out center tags;
        """

        try:
            resp = http_json(
                "POST", self.overpass_url,
                headers={"User-Agent": _ua(), "Accept": "application/json"},
                body={"data": overpass_query},
                timeout=40,
            )
        except Exception:
            return self._fallback_pois(city_name, geo, limit)

        elements = resp.get("elements", []) if isinstance(resp, dict) else []
        seen: set = set()
        pois: List[POIOption] = []

        for item in elements:
            tags = item.get("tags", {}) or {}
            name = tags.get("name") or tags.get("brand") or tags.get("operator")
            if not name:
                continue
            kind = tags.get("tourism") or tags.get("amenity") or tags.get("historic") or tags.get("leisure") or "poi"
            lat2, lon2 = self._element_latlon(item)
            if lat2 is None or lon2 is None:
                continue
            dedupe_key = (name.strip().lower(), str(kind).strip().lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            distance_km = _haversine_km(lat, lon, lat2, lon2)
            pois.append(POIOption(
                name=name, kind=str(kind),
                rating=self._score_poi(tags, distance_km),
                distance_km=round(distance_km, 3),
                url=f"https://www.openstreetmap.org/{item.get('type','node')}/{item.get('id','')}",
                raw={"generated": False, "lat": lat2, "lon": lon2},
            ))

        pois.sort(key=lambda p: (p.rating, -p.distance_km), reverse=True)
        return pois[:limit] if pois else self._fallback_pois(city_name, geo, limit)

    def get_weather(self, city_name: str) -> Optional[Dict[str, Any]]:
        geo = self.geocode(city_name)
        if not geo:
            return None
        params = {
            "latitude": geo["lat"], "longitude": geo["lon"],
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
            "timezone": "auto",
        }
        url = f"{self.open_meteo_url}?{urllib.parse.urlencode(params)}"
        try:
            resp = http_json("GET", url)
            if not isinstance(resp, dict):
                return None
            return {"location": geo["display_name"], "latitude": geo["lat"], "longitude": geo["lon"], "daily": resp.get("daily", {})}
        except Exception:
            return None

    def _fallback_pois(self, city_name: str, geo: Dict[str, Any], limit: int) -> List[POIOption]:
        demo = city_demo_by_name(city_name)
        lat, lon = geo["lat"], geo["lon"]
        return [
            POIOption(name=item["name"], kind=item["kind"], rating=float(item["rating"]),
                      distance_km=float(item["distance_km"]), url="",
                      raw={"generated": True, "lat": lat, "lon": lon, "source": "static_demo"})
            for item in demo["fallback_pois"][:limit]
        ]

    def _element_latlon(self, item: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        if "lat" in item and "lon" in item:
            return _safe_float(item.get("lat")), _safe_float(item.get("lon"))
        center = item.get("center") or {}
        if "lat" in center and "lon" in center:
            return _safe_float(center.get("lat")), _safe_float(center.get("lon"))
        return None, None

    def _score_poi(self, tags: Dict[str, Any], distance_km: float) -> float:
        score = 3.0
        tourism = str(tags.get("tourism", "")).lower()
        amenity = str(tags.get("amenity", "")).lower()
        historic = str(tags.get("historic", "")).lower()
        leisure = str(tags.get("leisure", "")).lower()
        if tourism in {"museum", "attraction", "gallery", "viewpoint", "zoo", "theme_park"}: score += 1.4
        if amenity in {"restaurant", "cafe", "bar", "pub"}: score += 0.7
        if historic: score += 0.8
        if leisure in {"park", "garden"}: score += 0.6
        if "name" in tags: score += 0.2
        if distance_km < 1.0: score += 0.8
        elif distance_km < 3.0: score += 0.4
        elif distance_km > 8.0: score -= 0.4
        return round(min(5.0, max(1.0, score)), 2)
