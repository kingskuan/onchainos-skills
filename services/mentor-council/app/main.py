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

from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import payments
from .engine import council, mentor
from .personas import PERSONAS, catalog

SERVICE_NAME = "Mentor Council"
VERSION = "0.1.0"
PAID_PATHS = ("/mentor", "/council", "/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(follow_redirects=True)
    yield
    await app.state.client.aclose()


app = FastAPI(title=SERVICE_NAME, version=VERSION, lifespan=lifespan)


@app.middleware("http")
async def x402_gate(request: Request, call_next):
    path = request.url.path
    if not payments.enabled() or not path.startswith(PAID_PATHS):
        return await call_next(request)
    resource, description = str(request.url), f"{SERVICE_NAME} — per-call fee"
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
            "enabled": payments.enabled(),
            "price": payments.config()["price"],
            "asset": payments.config()["asset"],
            "network": payments.config()["network"],
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
