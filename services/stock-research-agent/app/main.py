"""Stock Research Agent — FastAPI service.

Endpoints
  GET  /                     service info + MCP tool manifest
  GET  /health               liveness
  GET  /research/{ticker}    deep single-stock research (core)
  GET  /screener             Finviz-lite screen over a curated/custom universe
  POST /mcp                  MCP-style tool dispatch ({"tool","arguments"})

Payments: an optional x402 gate (env PAY_ENABLED=1) returns HTTP 402 with a
payment-requirements body, so this can later sit behind the OKX A2MCP/x402
buyer flow. Off by default so the service is usable while pricing is decided.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from . import edgar, payments
from .research import research
from .screener import DEFAULT_UNIVERSE, screen

SERVICE_NAME = "Stock Research Agent"
VERSION = "0.2.0"

# Paths that require payment when the x402 gate is enabled.
PAID_PATHS = ("/research", "/screener", "/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(follow_redirects=True)
    # warm the ticker map so the first request is fast
    try:
        await edgar.load_ticker_map(app.state.client)
    except Exception:  # noqa: BLE001
        pass
    yield
    await app.state.client.aclose()


app = FastAPI(title=SERVICE_NAME, version=VERSION, lifespan=lifespan)


@app.middleware("http")
async def x402_gate(request: Request, call_next):
    path = request.url.path
    if not payments.enabled() or not path.startswith(PAID_PATHS):
        return await call_next(request)

    resource = str(request.url)
    description = f"{SERVICE_NAME} — per-call fee"
    x_payment = request.headers.get("x-payment")

    if not x_payment:
        return JSONResponse(status_code=402, content=payments.requirements(resource, description))

    ok, reason, settlement = await payments.verify_and_settle(
        request.app.state.client, x_payment, resource, description
    )
    if not ok:
        body = payments.requirements(resource, description)
        body["error"] = reason
        return JSONResponse(status_code=402, content=body)

    response = await call_next(request)
    if settlement:
        response.headers["X-PAYMENT-RESPONSE"] = payments.encode_response(settlement)
    return response


def _tool_manifest() -> list[dict[str, Any]]:
    return [
        {
            "name": "research_stock",
            "description": (
                "Deep research on a single US-listed stock: 5-year financials, "
                "growth, valuation (P/E, P/S, P/B, EV/EBITDA), a financial-health "
                "score (Altman Z), and analyst targets."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
        {
            "name": "screen_stocks",
            "description": (
                "Screen a universe of stocks by market cap, valuation, margin, "
                "and revenue growth (Finviz-lite)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "tickers": {"type": "array", "items": {"type": "string"}},
                    "min_market_cap": {"type": "number"},
                    "max_pe": {"type": "number"},
                    "min_net_margin": {"type": "number"},
                    "min_revenue_cagr": {"type": "number"},
                },
            },
        },
    ]


@app.get("/")
async def root():
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "description": (
            "Free-data stock research API — deep single-stock analysis + "
            "screening, built on SEC EDGAR and Yahoo Finance."
        ),
        "endpoints": {
            "research": "/research/{ticker}",
            "screener": "/screener?min_market_cap=1e11&max_pe=30",
            "mcp": "POST /mcp",
        },
        "mcp_tools": _tool_manifest(),
        "payments": {
            "enabled": payments.enabled(),
            "price": payments.config()["price"],
            "asset": payments.config()["asset"],
            "network": payments.config()["network"],
            "scheme": "x402 (exact)",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/research/{ticker}")
async def research_endpoint(request: Request, ticker: str):
    return await research(request.app.state.client, ticker)


@app.get("/screener")
async def screener_endpoint(
    request: Request,
    tickers: str | None = Query(None, description="Comma-separated universe override"),
    min_market_cap: float | None = None,
    max_market_cap: float | None = None,
    max_pe: float | None = None,
    min_pe: float | None = None,
    max_ps: float | None = None,
    min_net_margin: float | None = None,
    min_revenue_cagr: float | None = None,
    limit: int = 25,
):
    universe = (
        [t.strip().upper() for t in tickers.split(",") if t.strip()]
        if tickers
        else DEFAULT_UNIVERSE
    )
    flt = {
        k: v
        for k, v in {
            "min_market_cap": min_market_cap,
            "max_market_cap": max_market_cap,
            "max_pe": max_pe,
            "min_pe": min_pe,
            "max_ps": max_ps,
            "min_net_margin": min_net_margin,
            "min_revenue_cagr": min_revenue_cagr,
        }.items()
        if v is not None
    }
    return await screen(request.app.state.client, universe, flt, limit=limit)


@app.post("/mcp")
async def mcp_endpoint(request: Request, body: dict[str, Any]):
    """Minimal MCP-style dispatch. body = {"tool": ..., "arguments": {...}}."""
    tool = body.get("tool") or body.get("name")
    args = body.get("arguments") or body.get("params") or {}
    client = request.app.state.client
    if tool == "research_stock":
        t = args.get("ticker")
        if not t:
            return JSONResponse(status_code=400, content={"error": "ticker required"})
        return await research(client, t)
    if tool == "screen_stocks":
        universe = args.get("tickers") or DEFAULT_UNIVERSE
        universe = [t.upper() for t in universe]
        flt = {
            k: args[k]
            for k in (
                "min_market_cap", "max_market_cap", "max_pe", "min_pe",
                "max_ps", "min_net_margin", "min_revenue_cagr",
            )
            if k in args and args[k] is not None
        }
        return await screen(client, universe, flt, limit=int(args.get("limit", 25)))
    return JSONResponse(
        status_code=404,
        content={"error": f"unknown tool: {tool}", "tools": [t["name"] for t in _tool_manifest()]},
    )
