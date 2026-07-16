"""Crypto Intel — FastAPI service (A2MCP ASP).

Token safety heuristics + cross-venue price spreads from public DexScreener data
(free, no key). Reimplements the ideas behind the Hermes skill-packs
(defi-security-scanner + crypto-arb) as on-demand, paid endpoints — flat $1/call.

Endpoints
  GET  /                          info + MCP manifest
  GET  /health                    liveness
  GET  /token/{address}           token safety scan (?chain=ethereum optional)
  GET  /spread?q=<symbol|address> cross-venue price spread
  POST /mcp                       MCP-style dispatch
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from . import okx_payment
from .intel import spread, token_safety

SERVICE_NAME = "Crypto Intel"
VERSION = "0.1.0"

# Flat $1 per call (as requested).
PAY_ROUTES = {
    "GET /token/*": okx_payment.route("1"),
    "GET /spread": okx_payment.route("1"),
    "POST /mcp": okx_payment.route("1"),
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
            "name": "token_safety",
            "description": (
                "Heuristic token safety scan from public DEX data: liquidity, "
                "buy/sell honeypot signal, pair age, FDV/liquidity, volatility → "
                "a 0-100 score, verdict, and flags. Args: address, chain (optional)."
            ),
            "input_schema": {"type": "object", "properties": {
                "address": {"type": "string"}, "chain": {"type": "string"}},
                "required": ["address"]},
        },
        {
            "name": "price_spread",
            "description": "Cross-venue price spread for a token (symbol or address) across DEXes.",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                             "required": ["query"]},
        },
    ]


@app.get("/")
async def root():
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "description": (
            "On-demand crypto intel: token safety heuristics + cross-venue price "
            "spreads from public DexScreener data. Read-only, not financial advice."
        ),
        "endpoints": {
            "token_safety": "/token/{address}?chain=ethereum",
            "spread": "/spread?q=PEPE",
            "mcp": "POST /mcp",
        },
        "mcp_tools": _tool_manifest(),
        "payments": {
            "enabled": PAYMENTS_ON,
            "scheme": "x402 (exact) via OKX facilitator",
            "network": os.getenv("PAY_NETWORK", "eip155:196"),
            "price": "$1 / call",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/token/{address}")
async def token_endpoint(request: Request, address: str, chain: str | None = Query(None)):
    try:
        return await token_safety(request.app.state.client, address, chain)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(e)[:160]})


@app.get("/spread")
async def spread_endpoint(request: Request, q: str = Query(...)):
    try:
        return await spread(request.app.state.client, q)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(e)[:160]})


@app.post("/mcp")
async def mcp_endpoint(request: Request, body: dict[str, Any]):
    tool = body.get("tool") or body.get("name")
    args = body.get("arguments") or body.get("params") or {}
    client = request.app.state.client
    if tool == "token_safety":
        if not args.get("address"):
            return JSONResponse(status_code=400, content={"error": "address required"})
        return await token_safety(client, args["address"], args.get("chain"))
    if tool == "price_spread":
        if not args.get("query"):
            return JSONResponse(status_code=400, content={"error": "query required"})
        return await spread(client, args["query"])
    return JSONResponse(status_code=404, content={"error": f"unknown tool: {tool}",
                        "tools": [t["name"] for t in _tool_manifest()]})
