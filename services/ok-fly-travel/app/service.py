from __future__ import annotations

from .clients import AmadeusClient, OpenTripMapClient, region_from_latlon
from .demo_data import city_demo_by_name
from .models import TripPlanResponse, TripRequest
from .optimizer import Optimizer
from .planner import Planner
from .presenter import Presenter


class TravelService:
    def __init__(self) -> None:
        self.planner = Planner()
        self.amadeus = AmadeusClient()
        self.otm = OpenTripMapClient()
        self.optimizer = Optimizer()
        self.presenter = Presenter()

    def run(self, req: TripRequest) -> TripPlanResponse:
        normalized = self.planner.normalize(req)
        city_code = self.planner.infer_city_code(normalized.destination)

        # Resolve the destination ONCE against live geocoding. Every downstream
        # component (flights, hotels, POIs, weather) is keyed off this single
        # resolution so they can never disagree — the previous bug was flights/
        # hotels defaulting to Tokyo while only weather used the real coordinates.
        geo = self.otm.geocode(normalized.destination)
        if geo:
            display_name = geo.get("display_name") or normalized.destination
            region = region_from_latlon(geo.get("lat"), geo.get("lon"))
            resolved = True
        else:
            display_name = normalized.destination
            region = "global"
            resolved = False

        city_demo = city_demo_by_name(normalized.destination)

        flights = self.amadeus.search_flights(
            origin=normalized.origin, destination=city_code,
            start_date=normalized.start_date, adults=normalized.travelers,
            currency="USD", max_results=5,
            display_name=display_name, region=region,
        )
        hotels = self.amadeus.search_hotels(
            city_code=city_code, check_in=normalized.start_date,
            check_out=normalized.end_date, adults=normalized.travelers, max_results=8,
            display_name=display_name, region=region,
        )
        # POIs + weather only when we actually resolved the destination — never
        # from a fallback city's coordinates.
        pois = self.otm.search_pois(normalized.destination, limit=12) if resolved else []
        weather = self.otm.get_weather(normalized.destination) if resolved else None

        plans = self.optimizer.build_candidates(
            normalized, flights, hotels, pois,
            display_name=display_name, city_code=city_code, resolved=resolved,
        )

        return TripPlanResponse(
            request=normalized,
            research={
                "destination_input": normalized.destination,
                "resolved_destination": display_name,
                "destination_resolved": resolved,
                "city_code": city_code,
                "city_code_known": self.planner.is_known_city(normalized.destination),
                "region": region,
                "city_demo": {
                    "display_name": city_demo["display_name"],
                    "crypto_friendly": city_demo["crypto_friendly"],
                },
                "flight_count": len(flights),
                "hotel_count": len(hotels),
                "poi_count": len(pois),
                "poi_source": "live_osm_overpass" if pois else ("unresolved" if not resolved else "none_found"),
                "weather": weather,
                "notes": (
                    []
                    if resolved
                    else ["Destination could not be geolocated; POIs/weather omitted "
                          "and flight/hotel estimates use a generic pricing band."]
                ),
            },
            json=self.presenter.render_json(plans),
            markdown=self.presenter.render_markdown(plans, resolved=resolved,
                                                    resolved_name=display_name),
            best_plan=plans[0] if plans else None,
        )
