from __future__ import annotations

from typing import Any, Dict

from .a2a_contract import get_a2a_service_contract
from .models import TripRequest
from .service import TravelService


class A2AAdapter:
    def __init__(self, service: TravelService) -> None:
        self.service = service

    def manifest(self) -> Dict[str, Any]:
        return get_a2a_service_contract()

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = TripRequest.model_validate(payload)
        result = self.service.run(req)
        return result.model_dump()
