from __future__ import annotations

from .clients import AmadeusClient, OpenTripMapClient
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
        city_demo = city_demo_by_name(normalized.destination)

        flights = self.amadeus.search_flights(
            origin=normalized.origin, destination=city_code,
            start_date=normalized.start_date, adults=normalized.travelers,
            currency="USD", max_results=5,
        )
        hotels = self.amadeus.search_hotels(
            city_code=city_code, check_in=normalized.start_date,
            check_out=normalized.end_date, adults=normalized.travelers, max_results=8,
        )
        pois = self.otm.search_pois(normalized.destination, limit=12)
        weather = self.otm.get_weather(normalized.destination)

        plans = self.optimizer.build_candidates(normalized, flights, hotels, pois)

        return TripPlanResponse(
            request=normalized,
            research={
                "city_code": city_code,
                "city_demo": {
                    "display_name": city_demo["display_name"],
                    "crypto_friendly": city_demo["crypto_friendly"],
                },
                "flight_count": len(flights),
                "hotel_count": len(hotels),
                "poi_count": len(pois),
                "weather": weather,
            },
            json=self.presenter.render_json(plans),
            markdown=self.presenter.render_markdown(plans),
            best_plan=plans[0] if plans else None,
        )
