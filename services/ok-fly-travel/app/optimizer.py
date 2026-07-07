from __future__ import annotations

from typing import List, Optional

from .models import FlightOption, HotelOption, Plan, POIOption, TripRequest
from .planner import Planner


CRYPTO_FRIENDLY_DB = {
    "tokyo":     {"city_tags": ["high_card_acceptance","tech_friendly","web3_presence"],     "notes": ["Prefer card-friendly hotels. Strong fit for Web3/crypto-native travelers."]},
    "singapore": {"city_tags": ["cashless","fintech_hub","safe_transit"],                    "notes": ["Excellent cashless infrastructure. Good for business travel."]},
    "hong kong": {"city_tags": ["card_acceptance","dense_city","web3_presence"],             "notes": ["Best for short trips, nightlife, and efficient transit."]},
    "bangkok":   {"city_tags": ["budget_friendly","street_food","growing_fintech"],          "notes": ["Excellent value destination. Growing crypto ATM presence."]},
    "seoul":     {"city_tags": ["tech_hub","cashless","crypto_friendly"],                    "notes": ["High crypto adoption. Strong cashless payment infrastructure."]},
    "dubai":     {"city_tags": ["luxury","international","crypto_regulation_friendly"],      "notes": ["Dubai has crypto-friendly regulations. Premium destination."]},
    "paris":     {"city_tags": ["card_acceptance","cultural_hub","eu_regulation"],           "notes": ["Strong card acceptance. EU crypto regulation context."]},
    "london":    {"city_tags": ["fintech_hub","card_acceptance","web3_events"],              "notes": ["Major fintech and Web3 events hub."]},
    "new york":  {"city_tags": ["financial_hub","high_card_acceptance","crypto_events"],     "notes": ["Major crypto events hub. Strong financial infrastructure."]},
}


def crypto_friendly_context(destination: str) -> dict:
    key = destination.strip().lower()
    for city, data in CRYPTO_FRIENDLY_DB.items():
        if city in key or key in city:
            return data
    return {
        "city_tags": ["cashless_recommended", "card_payment_check"],
        "notes": ["Use heuristic crypto-friendly labels as advisory only."],
    }


class Optimizer:
    def __init__(self) -> None:
        self.planner = Planner()

    def score_flight(self, flight: FlightOption, req: TripRequest) -> float:
        budget_factor = max(0.0, 1.0 - (flight.price_usd / max(req.budget_usd, 1.0))) if req.budget_usd > 0 else 0.5
        duration_factor = max(0.0, 1.0 - flight.duration_minutes / 1800.0)
        return 0.55 * budget_factor + 0.45 * duration_factor

    def score_hotel(self, hotel: HotelOption, req: TripRequest) -> float:
        days = self.planner.trip_days(req)
        if req.budget_usd <= 0:
            budget_factor = 0.5
        else:
            nightly_budget = req.budget_usd / max(1, days)
            budget_factor = max(0.0, 1.0 - (hotel.price_usd_per_night / max(nightly_budget, 1.0)))
        rating_factor = min(max(hotel.score / 5.0, 0.0), 1.0)
        return 0.65 * budget_factor + 0.35 * rating_factor

    def build_candidates(
        self,
        req: TripRequest,
        flights: List[FlightOption],
        hotels: List[HotelOption],
        pois: List[POIOption],
        display_name: Optional[str] = None,
        city_code: Optional[str] = None,
        resolved: bool = True,
    ) -> List[Plan]:
        days = self.planner.trip_days(req)
        crypto = crypto_friendly_context(req.destination)
        dest_label = display_name or req.destination
        code = city_code or self.planner.infer_city_code(req.destination)
        ranked_flights = sorted(flights, key=lambda f: self.score_flight(f, req), reverse=True)[:3] or [None]
        ranked_hotels = sorted(hotels, key=lambda h: self.score_hotel(h, req), reverse=True)[:3] or [None]
        poi_days = self._assign_pois(pois, days, req.pace)

        plans: List[Plan] = []
        for flight in ranked_flights:
            for hotel in ranked_hotels:
                flight_cost = flight.price_usd if flight else 0.0
                hotel_cost = (hotel.price_usd_per_night * days) if hotel else 0.0
                local_spend = self._estimate_local_spend(days, req.pace, req.trip_type, req.preferences)
                total = flight_cost + hotel_cost + local_spend

                score = 0.0
                score += self.score_flight(flight, req) if flight else 0.0
                score += self.score_hotel(hotel, req) if hotel else 0.0
                score += self._score_itinerary(poi_days, req)
                if req.budget_usd > 0 and total > req.budget_usd:
                    score -= min(1.0, (total - req.budget_usd) / req.budget_usd)

                assumptions = [
                    f"Destination '{req.destination}' resolved to {dest_label} (code {code}).",
                    "Flight & hotel prices are simulated estimates (no live booking API) — "
                    "not bookable fares. POIs & weather are from live public sources.",
                    "Crypto-friendly labels are heuristic and advisory only.",
                ]
                if not resolved:
                    assumptions.insert(1, "WARNING: destination could not be geolocated; "
                                          "estimates use a generic pricing band and POIs/weather are omitted.")

                plans.append(Plan(
                    title=f"{dest_label} {req.start_date}→{req.end_date} {req.trip_type.title()} Plan",
                    summary=(
                        f"{req.trip_type} trip to {dest_label} for {req.travelers} traveler(s), "
                        f"pace={req.pace}. Est. total ${round(total,2)} (simulated). "
                        f"Tags: {', '.join(crypto['city_tags'])}."
                    ),
                    flight=flight,
                    hotel=hotel,
                    pois_by_day=poi_days,
                    budget_breakdown={
                        "flight": round(flight_cost, 2),
                        "hotel": round(hotel_cost, 2),
                        "local_spend": round(local_spend, 2),
                        "estimated_total": round(total, 2),
                    },
                    crypto_friendly_notes=crypto["notes"],
                    score=score,
                    assumptions=assumptions,
                ))

        return sorted(plans, key=lambda p: p.score, reverse=True)[:3]

    def _assign_pois(self, pois: List[POIOption], days: int, pace: str) -> List[List[POIOption]]:
        if not pois:
            return [[] for _ in range(days)]
        per_day = 3 if pace == "relaxed" else 6 if pace == "packed" else 4
        sorted_pois = sorted(pois, key=lambda p: (p.rating, -p.distance_km), reverse=True)
        out = []
        idx = 0
        for _ in range(days):
            out.append(sorted_pois[idx: idx + per_day])
            idx = (idx + per_day) % len(sorted_pois)
        return out

    def _score_itinerary(self, daily_pois: List[List[POIOption]], req: TripRequest) -> float:
        if not daily_pois:
            return 0.0
        target = 3.0 if req.pace == "relaxed" else 6.0 if req.pace == "packed" else 4.0
        total = sum(max(0.0, 1.0 - abs(len(day) - target) / max(target, 1.0)) for day in daily_pois)
        return total / len(daily_pois)

    def _estimate_local_spend(self, days: int, pace: str, trip_type: str, preferences: List[str]) -> float:
        base = 80.0 * days
        if pace == "packed": base *= 1.25
        elif pace == "relaxed": base *= 0.9
        if "fine dining" in preferences or "restaurant" in preferences: base += 60.0 * days
        if trip_type == "family": base += 40.0 * days
        return base
