"""Breakout Scanner — FastAPI service.

On-demand version of BreakoutAnalysis: scan the whole US market for volume
breakouts, gate on long-term quality, and get an AI plain-English read + news
per mover, plus a market briefing. Built to run as a paid A2MCP ASP endpoint.

Endpoints
  GET  /                     info + MCP manifest
  GET  /health               liveness
  GET  /scan                 whole-market breakout scan (configurable filters)
  GET  /analyze/{ticker}     AI breakout analysis + news + quality for a mover
  GET  /briefing             market briefing (indices + AI summary)
  POST /mcp                  MCP-style dispatch
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from . import okx_payment
from .analysis import analyze_breakout, briefing, quality_gate
from .screener import scan

SERVICE_NAME = "Breakout Scanner"
VERSION = "0.1.0"

PAY_ROUTES = {
    "GET /scan": okx_payment.route("0.1"),
    "GET /analyze/*": okx_payment.route("0.05"),
    "GET /briefing": okx_payment.route("0.05"),
    "POST /mcp": okx_payment.route("0.1"),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(follow_redirects=True)
    yield
    await app.state.client.aclose()


app = FastAPI(title=SERVICE_NAME, version=VERSION, lifespan=lifespan)
PAYMENTS_ON = okx_payment.install(app, PAY_ROUTES)


def _tool_manifest() -> list[dict[str, Any]]:
    return [
        {
            "name": "scan_breakouts",
            "description": (
                "Scan the entire US market for volume-driven breakouts (big % move "
                "on unusual volume). Optional filters: min_change_percent, min_volume, "
                "min_relative_volume, min_price, max_price, min_market_cap, quality "
                "(true to keep only long-term-strong names)."
            ),
            "input_schema": {"type": "object", "properties": {
                "min_change_percent": {"type": "number"},
                "min_relative_volume": {"type": "number"},
                "quality": {"type": "boolean"},
                "limit": {"type": "integer"},
            }},
        },
        {
            "name": "analyze_breakout",
            "description": "AI plain-English read on why a stock is moving + recent news + quality gate.",
            "input_schema": {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
        },
        {
            "name": "market_briefing",
            "description": "Market briefing: S&P/NASDAQ/Dow/VIX levels + an AI summary.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]


@app.get("/")
async def root():
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "description": (
            "On-demand US-market breakout scanner: volume breakouts + long-term "
            "quality gate + AI analysis with news + market briefing."
        ),
        "endpoints": {
            "scan": "/scan?min_change_percent=6&min_relative_volume=2&quality=true",
            "analyze": "/analyze/{ticker}",
            "briefing": "/briefing",
            "mcp": "POST /mcp",
        },
        "mcp_tools": _tool_manifest(),
        "payments": {
            "enabled": PAYMENTS_ON,
            "scheme": "x402 (exact) via OKX facilitator",
            "network": os.getenv("PAY_NETWORK", "eip155:196"),
            "prices": {"scan": "$0.1", "analyze": "$0.05", "briefing": "$0.05"},
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


def _flt(min_change_percent, min_volume, min_relative_volume, min_price, max_price, min_market_cap):
    f = {}
    if min_change_percent is not None:
        f["min_change_percent"] = min_change_percent
    if min_volume is not None:
        f["min_volume"] = min_volume
    if min_relative_volume is not None:
        f["min_relative_volume"] = min_relative_volume
    if min_price is not None:
        f["min_price"] = min_price
    if max_price is not None:
        f["max_price"] = max_price
    if min_market_cap is not None:
        f["min_market_cap"] = min_market_cap
    return f


async def _apply_quality(client, result: dict[str, Any]) -> dict[str, Any]:
    """Run the historical-quality gate over scan hits, keep the strong ones."""
    rows = result.get("breakouts", [])
    gates = await asyncio.gather(*[quality_gate(client, r["ticker"]) for r in rows])
    kept = []
    for r, g in zip(rows, gates):
        if g.get("pass"):
            r = {**r, "quality": {k: g.get(k) for k in ("one_year_return", "pct_of_52w_range")}}
            kept.append(r)
    result["breakouts"] = kept
    result["count"] = len(kept)
    result["quality_gate"] = "applied (Yahoo 1y)"
    return result


@app.get("/scan")
async def scan_endpoint(
    request: Request,
    min_change_percent: float | None = None,
    min_volume: int | None = None,
    min_relative_volume: float | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_market_cap: float | None = None,
    quality: bool = False,
    limit: int = Query(30, le=100),
):
    client = request.app.state.client
    flt = _flt(min_change_percent, min_volume, min_relative_volume, min_price, max_price, min_market_cap)
    try:
        result = await scan(client, flt, limit=limit)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(e)[:160]})
    if quality and result.get("breakouts"):
        result = await _apply_quality(client, result)
    return result


@app.get("/analyze/{ticker}")
async def analyze_endpoint(request: Request, ticker: str):
    return await analyze_breakout(request.app.state.client, ticker)


@app.get("/briefing")
async def briefing_endpoint(request: Request):
    return await briefing(request.app.state.client)


@app.post("/mcp")
async def mcp_endpoint(request: Request, body: dict[str, Any]):
    tool = body.get("tool") or body.get("name")
    args = body.get("arguments") or body.get("params") or {}
    client = request.app.state.client
    if tool == "scan_breakouts":
        flt = _flt(args.get("min_change_percent"), args.get("min_volume"),
                   args.get("min_relative_volume"), args.get("min_price"),
                   args.get("max_price"), args.get("min_market_cap"))
        result = await scan(client, flt, limit=int(args.get("limit", 30)))
        if args.get("quality") and result.get("breakouts"):
            result = await _apply_quality(client, result)
        return result
    if tool == "analyze_breakout":
        if not args.get("ticker"):
            return JSONResponse(status_code=400, content={"error": "ticker required"})
        return await analyze_breakout(client, args["ticker"])
    if tool == "market_briefing":
        return await briefing(client)
    return JSONResponse(status_code=404, content={"error": f"unknown tool: {tool}",
                        "tools": [t["name"] for t in _tool_manifest()]})
