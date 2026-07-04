"""Mentor Council — FastAPI service.

Decision advice through methodology frameworks (inspired by public thinkers,
branded by method — never impersonating anyone). Single-mentor answers plus a
council roundtable that debates your question across frameworks.

Endpoints
  GET  /                      service info + catalog + MCP manifest
  GET  /health                liveness
  GET  /mentors               list available methodology frameworks
  POST /mentor/{key}          one framework's take   {"question": "..."}
  POST /council               roundtable/debate      {"question": "...", "k": 3}
  POST /mcp                   MCP-style dispatch

Optional x402 payment gate (env PAY_ENABLED=1).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import okx_payment
from .engine import council, mentor
from .personas import PERSONAS, catalog

SERVICE_NAME = "Mentor Council"
VERSION = "0.2.0"

# x402 pricing per protected route (X Layer, USDT). The flagship council is the
# premium product; single-mentor calls are cheap.
PAY_ROUTES = {
    "POST /council": okx_payment.route("1.5"),
    "POST /mcp": okx_payment.route("1.5"),
    "POST /mentor/*": okx_payment.route("0.3"),
    "POST /m/*/mcp": okx_payment.route("0.3"),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(follow_redirects=True)
    yield
    await app.state.client.aclose()


app = FastAPI(title=SERVICE_NAME, version=VERSION, lifespan=lifespan)

# Real OKX x402 gate (official okxweb3-app-x402). Off until facilitator creds +
# PAY_TO are set — see app/okx_payment.py.
PAYMENTS_ON = okx_payment.install(app, PAY_ROUTES)


def _tool_manifest() -> list[dict[str, Any]]:
    return [
        {
            "name": "council",
            "description": (
                "Roundtable: routes your question to the most relevant methodology "
                "frameworks, each gives its take, then synthesizes a verdict and shows "
                "where they disagree. The flagship product."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "k": {"type": "integer"},
                    "mentors": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question"],
            },
        },
        {
            "name": "mentor",
            "description": "One methodology framework's take on your question.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "enum": list(PERSONAS)},
                    "question": {"type": "string"},
                },
                "required": ["key", "question"],
            },
        },
    ]


@app.get("/")
async def root():
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "description": (
            "Decision advice via methodology frameworks (inspired by public thinkers, "
            "branded by method — not impersonation). Single takes + a debating council."
        ),
        "mentors": catalog(),
        "mcp_tools": _tool_manifest(),
        "payments": {
            "enabled": PAYMENTS_ON,
            "scheme": "x402 (exact) via OKX facilitator",
            "network": os.getenv("PAY_NETWORK", "eip155:196"),
            "prices": {"council": "$1.5", "mentor": "$0.3"},
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/mentors")
async def mentors():
    return {"mentors": catalog()}


@app.post("/mentor/{key}")
async def mentor_endpoint(request: Request, key: str, body: dict[str, Any]):
    q = (body or {}).get("question", "").strip()
    if not q:
        return JSONResponse(status_code=400, content={"error": "question required"})
    return await mentor(request.app.state.client, key, q)


@app.post("/council")
async def council_endpoint(request: Request, body: dict[str, Any]):
    q = (body or {}).get("question", "").strip()
    if not q:
        return JSONResponse(status_code=400, content={"error": "question required"})
    k = int((body or {}).get("k", 3))
    mentors_arg = (body or {}).get("mentors")
    return await council(request.app.state.client, q, k=k, mentors=mentors_arg)


@app.post("/m/{key}/mcp")
async def per_mentor_mcp(request: Request, key: str, body: dict[str, Any]):
    """Per-mentor MCP endpoint — one distinct A2MCP endpoint per methodology ASP."""
    args = body.get("arguments") or body.get("params") or {}
    q = (args.get("question") or body.get("question") or "").strip()
    if not q:
        return JSONResponse(status_code=400, content={"error": "question required"})
    return await mentor(request.app.state.client, key, q)


@app.post("/mcp")
async def mcp_endpoint(request: Request, body: dict[str, Any]):
    tool = body.get("tool") or body.get("name")
    args = body.get("arguments") or body.get("params") or {}
    client = request.app.state.client
    q = (args.get("question") or "").strip()
    if tool == "council":
        if not q:
            return JSONResponse(status_code=400, content={"error": "question required"})
        return await council(client, q, k=int(args.get("k", 3)), mentors=args.get("mentors"))
    if tool == "mentor":
        if not args.get("key") or not q:
            return JSONResponse(status_code=400, content={"error": "key + question required"})
        return await mentor(client, args["key"], q)
    return JSONResponse(
        status_code=404,
        content={"error": f"unknown tool: {tool}", "tools": [t["name"] for t in _tool_manifest()]},
    )
