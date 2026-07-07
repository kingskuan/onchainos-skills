from __future__ import annotations

from fastapi import FastAPI, HTTPException

from . import okx_payment
from .a2a_adapter import A2AAdapter
from .models import TripPlanResponse, TripRequest
from .service import TravelService

app = FastAPI(title="Crypto-Friendly Travel Planner ASP", version="0.3.0")
service = TravelService()
a2a = A2AAdapter(service)

# OKX Pay (x402) — $5/call on the paid work routes; /health + manifests stay
# free for discovery. Off until OKX_API_KEY/SECRET/PASSPHRASE + PAY_TO are set.
PAY_ROUTES = {
    "POST /plan": okx_payment.route("5"),
    "POST /a2a/invoke": okx_payment.route("5"),
}
PAYMENTS_ON = okx_payment.install(app, PAY_ROUTES)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/a2a/manifest")
def a2a_manifest() -> dict:
    return a2a.manifest()


@app.get("/service/manifest")
def service_manifest() -> dict:
    return a2a.manifest()


@app.post("/plan", response_model=TripPlanResponse)
def plan_trip(req: TripRequest) -> TripPlanResponse:
    return service.run(req)


@app.post("/a2a/invoke")
def a2a_invoke(payload: dict) -> dict:
    try:
        return a2a.invoke(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
