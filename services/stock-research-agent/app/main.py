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

import os

from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from . import edgar, okx_payment
from .analyst import analyze_stock
from .research import research
from .screener import DEFAULT_UNIVERSE, screen

SERVICE_NAME = "Stock Research Agent"
VERSION = "0.4.0"

# x402 pricing per protected route (X Layer, USDT). AI analyst is the premium.
PAY_ROUTES = {
    "GET /research/*": okx_payment.route("0.05"),
    "GET /screener": okx_payment.route("0.1"),
    "GET /analyze/*": okx_payment.route("0.5"),
    # Registered ASP endpoint (on-chain fee = $2). The 402 challenge price MUST
    # match the fee buyers see in the marketplace, per the OKX Agent payment
    # protocol standard — otherwise listing review rejects the service.
    "POST /mcp": okx_payment.route("2"),
}


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

# Real OKX x402 gate — off until facilitator creds + PAY_TO are set.
PAYMENTS_ON = okx_payment.install(app, PAY_ROUTES)


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
            "name": "analyze_stock",
            "description": (
                "AI analyst verdict on a stock: a bull-vs-bear debate grounded "
                "on the company's financials/valuation/health/segments, plus a "
                "rating (STRONG_BUY..STRONG_SELL), confidence, thesis, and risks. "
                "Requires an LLM key configured on the server."
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
            "enabled": PAYMENTS_ON,
            "scheme": "x402 (exact) via OKX facilitator",
            "network": os.getenv("PAY_NETWORK", "eip155:196"),
            "prices": {"research": "$0.05", "screener": "$0.1", "analyze": "$0.5"},
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/research/{ticker}")
async def research_endpoint(request: Request, ticker: str):
    return await research(request.app.state.client, ticker)


@app.get("/analyze/{ticker}")
async def analyze_endpoint(request: Request, ticker: str):
    """AI analyst: bull vs bear debate + verdict, grounded on our data."""
    return await analyze_stock(request.app.state.client, ticker)


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
    if tool == "analyze_stock":
        t = args.get("ticker")
        if not t:
            return JSONResponse(status_code=400, content={"error": "ticker required"})
        return await analyze_stock(client, t)
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
