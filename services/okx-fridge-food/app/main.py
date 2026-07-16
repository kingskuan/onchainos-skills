from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import okx_payment
from .a2a import A2AAdapter, get_manifest
from .models import RecipeRequest, RecipeResponse
from .service import RecipeService

app = FastAPI(title="FridgeFood ASP", version="1.0.0")
service = RecipeService()
a2a = A2AAdapter(service)

# OKX Pay (x402) — $1/call on the paid work routes; /health + manifests stay free
# for discovery. Off until OKX_API_KEY/SECRET/PASSPHRASE + PAY_TO are set.
PAY_ROUTES = {
    "POST /cook": okx_payment.route("1"),
    "POST /a2a/invoke": okx_payment.route("1"),
    "POST /mcp": okx_payment.route("1"),
}
PAYMENTS_ON = okx_payment.install(app, PAY_ROUTES)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/a2a/manifest")
def manifest() -> dict:
    return a2a.manifest()


@app.get("/service/manifest")
def service_manifest() -> dict:
    return a2a.manifest()


@app.get("/")
def root() -> dict:
    m = a2a.manifest()
    return {"service": m["display_name"], "version": m["version"],
            "capabilities": m["capabilities"], "payments_enabled": PAYMENTS_ON,
            "manifest": "/a2a/manifest"}


@app.post("/cook", response_model=RecipeResponse)
def cook(req: RecipeRequest) -> RecipeResponse:
    return service.run(req)


@app.post("/a2a/invoke")
def invoke(payload: dict) -> dict:
    try:
        return a2a.invoke(payload)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/mcp")
def mcp(body: Dict[str, Any]) -> Any:
    """MCP-style dispatch: {"tool": "cook", "arguments": {"ingredients": [...]}}."""
    args = dict(body.get("arguments") or body.get("params") or {})
    try:
        req = RecipeRequest.model_validate(args)
        return service.run(req).model_dump()
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"error": str(e)})
