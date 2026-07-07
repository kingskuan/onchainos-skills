from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    origin: str = Field(..., description="IATA code, e.g. HKG")
    destination: str = Field(..., description="City name or IATA code")
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    travelers: int = Field(1, ge=1)
    budget_usd: float = Field(0.0, ge=0.0)
    preferences: List[str] = Field(default_factory=list)
    pace: str = Field("balanced", pattern="^(relaxed|balanced|packed)$")
    trip_type: str = Field("leisure", pattern="^(leisure|business|family|honeymoon|solo)$")


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
