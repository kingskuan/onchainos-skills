from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class TripRequest(BaseModel):
    # Accept both snake_case and camelCase (and a few common synonyms) so a buyer
    # agent that sends `startDate`/`checkIn`/`budget` does NOT 422 *after* x402 has
    # already settled payment. That mismatch previously caused a paid-for-nothing
    # call + a second charge on retry. populate_by_name keeps field-name access
    # working everywhere else; extra="ignore" tolerates unknown keys.
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    origin: str = Field(
        ..., description="City name or IATA code, e.g. HKG",
        validation_alias=AliasChoices("origin", "from", "from_city", "departure"))
    destination: str = Field(
        ..., description="City name or IATA code",
        validation_alias=AliasChoices("destination", "to", "to_city", "dest"))
    start_date: str = Field(
        ..., description="YYYY-MM-DD",
        validation_alias=AliasChoices("start_date", "startDate", "check_in", "checkIn", "from_date"))
    end_date: str = Field(
        ..., description="YYYY-MM-DD",
        validation_alias=AliasChoices("end_date", "endDate", "check_out", "checkOut", "to_date"))
    travelers: int = Field(
        1, ge=1,
        validation_alias=AliasChoices("travelers", "travellers", "adults", "pax"))
    budget_usd: float = Field(
        0.0, ge=0.0,
        validation_alias=AliasChoices("budget_usd", "budgetUsd", "budget"))
    preferences: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("preferences", "prefs"))
    pace: str = Field("balanced", pattern="^(relaxed|balanced|packed)$")
    trip_type: str = Field(
        "leisure", pattern="^(leisure|business|family|honeymoon|solo)$",
        validation_alias=AliasChoices("trip_type", "tripType"))


class FlightOption(BaseModel):
    provider: str
    departure: str
    arrival: str
    duration_minutes: int
    price_usd: float
    currency: str
    itinerary_id: str
    raw: Dict[str, Any] = Field(default_factory=dict)


class HotelOption(BaseModel):
    provider: str
    name: str
    city_code: str
    price_usd_per_night: float
    score: float
    address: str = ""
    raw: Dict[str, Any] = Field(default_factory=dict)


class POIOption(BaseModel):
    name: str
    kind: str
    rating: float
    distance_km: float
    url: str = ""
    raw: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    title: str
    summary: str
    flight: Optional[FlightOption] = None
    hotel: Optional[HotelOption] = None
    pois_by_day: List[List[POIOption]]
    budget_breakdown: Dict[str, float]
    crypto_friendly_notes: List[str]
    score: float
    assumptions: List[str] = Field(default_factory=list)


class TripPlanResponse(BaseModel):
    request: TripRequest
    research: Dict[str, Any]
    json: Dict[str, Any]
    markdown: str
    best_plan: Optional[Plan] = None
    # Transparency: flights/hotels are simulated estimates (no live booking API),
    # while POIs + weather come from live free sources (OSM/Overpass, Open-Meteo).
    # data_mode makes this explicit instead of presenting mock data as bookable.
    data_mode: str = "simulated_flights_hotels+live_poi_weather"
    disclaimer: str = (
        "Flight and hotel options are DETERMINISTIC ESTIMATES for planning only — "
        "not live availability or bookable fares. POIs and weather are pulled from "
        "live public sources for the resolved destination. Verify prices before booking."
    )
