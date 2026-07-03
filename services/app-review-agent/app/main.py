"""App Review Analysis Agent — FastAPI service.

Read-only analysis of PUBLIC app-store reviews (App Store + Google Play):
rating trends, sentiment, themes users love vs complain about, extracted bugs
and feature requests, and competitor comparison. No posting, no manipulation.

Endpoints
  GET  /                       service info + MCP tool manifest
  GET  /health                 liveness
  GET  /app/search             find an app id/package by name
  GET  /reviews                raw recent reviews
  GET  /analyze                full review analysis (core)
  GET  /compare                compare several apps side by side
  POST /mcp                    MCP-style tool dispatch

Optional x402 payment gate (env PAY_ENABLED=1) — see app/payments.py.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from . import analyze as analyzer
from . import apple, googleplay, payments

SERVICE_NAME = "App Review Analysis Agent"
VERSION = "0.1.0"
PAID_PATHS = ("/analyze", "/reviews", "/compare", "/mcp")


def _platform(p: str):
    p = (p or "ios").lower()
    if p in ("ios", "apple", "appstore", "app-store"):
        return apple
    if p in ("android", "google", "googleplay", "play"):
        return googleplay
    return None


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
            "name": "analyze_app_reviews",
            "description": (
                "Analyze public reviews for an app: rating distribution & trend, "
                "sentiment, themes users love vs complain about, extracted bugs "
                "and feature requests. platform=ios|android, app_id=Apple numeric "
                "id or Android package name."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "enum": ["ios", "android"]},
                    "app_id": {"type": "string"},
                    "country": {"type": "string"},
                    "pages": {"type": "integer"},
                },
                "required": ["platform", "app_id"],
            },
        },
        {
            "name": "search_app",
            "description": "Find an app id/package by name. platform=ios|android.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "term": {"type": "string"},
                    "country": {"type": "string"},
                },
                "required": ["platform", "term"],
            },
        },
        {
            "name": "compare_apps",
            "description": "Compare several apps: rating, sentiment, top complaints.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "app_ids": {"type": "array", "items": {"type": "string"}},
                    "country": {"type": "string"},
                },
                "required": ["platform", "app_ids"],
            },
        },
    ]


@app.get("/")
async def root():
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "description": (
            "Read-only analysis of public App Store & Google Play reviews — "
            "sentiment, themes, bugs, feature requests, competitor comparison."
        ),
        "endpoints": {
            "search": "/app/search?platform=ios&term=whatsapp",
            "reviews": "/reviews?platform=ios&app_id=310633997",
            "analyze": "/analyze?platform=ios&app_id=310633997&pages=5",
            "compare": "/compare?platform=ios&app_ids=310633997,1386412985",
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


@app.get("/app/search")
async def app_search(
    request: Request,
    platform: str = "ios",
    term: str = Query(...),
    country: str = "us",
):
    mod = _platform(platform)
    if not mod:
        return JSONResponse(status_code=400, content={"error": "platform must be ios or android"})
    try:
        results = await mod.search(request.app.state.client, term, country)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(e)[:160]})
    return {"platform": platform, "term": term, "results": results}


@app.get("/reviews")
async def reviews_endpoint(
    request: Request,
    platform: str = "ios",
    app_id: str = Query(...),
    country: str = "us",
    pages: int = 3,
):
    mod = _platform(platform)
    if not mod:
        return JSONResponse(status_code=400, content={"error": "platform must be ios or android"})
    try:
        revs = await mod.reviews(request.app.state.client, app_id, country, pages)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(e)[:160]})
    return {"platform": platform, "app_id": app_id, "country": country, "count": len(revs), "reviews": revs}


async def _analyze(client, mod, app_id: str, country: str, pages: int) -> dict[str, Any]:
    meta, revs = await asyncio.gather(
        mod.lookup(client, app_id, country),
        mod.reviews(client, app_id, country, pages),
    )
    meta = meta or {"app_id": app_id}
    return analyzer.analyze(meta, revs)


@app.get("/analyze")
async def analyze_endpoint(
    request: Request,
    platform: str = "ios",
    app_id: str = Query(...),
    country: str = "us",
    pages: int = 5,
):
    mod = _platform(platform)
    if not mod:
        return JSONResponse(status_code=400, content={"error": "platform must be ios or android"})
    try:
        return await _analyze(request.app.state.client, mod, app_id, country, pages)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(e)[:160]})


@app.get("/compare")
async def compare_endpoint(
    request: Request,
    platform: str = "ios",
    app_ids: str = Query(..., description="Comma-separated app ids / packages"),
    country: str = "us",
    pages: int = 3,
):
    mod = _platform(platform)
    if not mod:
        return JSONResponse(status_code=400, content={"error": "platform must be ios or android"})
    ids = [x.strip() for x in app_ids.split(",") if x.strip()]
    client = request.app.state.client

    async def one(aid: str):
        try:
            a = await _analyze(client, mod, aid, country, pages)
            return {
                "app_id": aid,
                "name": a["app"].get("name"),
                "overall_rating": a.get("overall_rating"),
                "sample_avg_rating": a.get("sample_avg_rating"),
                "negative_pct": a["sentiment"]["negative"]["pct"],
                "top_complaints": [t["term"] for t in a["complaint_themes"][:5]],
                "top_issues": list(dict.fromkeys(i["keyword"] for i in a["top_issues"]))[:5],
                "trend": a["rating_trend"].get("direction"),
            }
        except Exception as e:  # noqa: BLE001
            return {"app_id": aid, "error": str(e)[:120]}

    rows = await asyncio.gather(*[one(i) for i in ids])
    return {"platform": platform, "country": country, "apps": rows}


@app.post("/mcp")
async def mcp_endpoint(request: Request, body: dict[str, Any]):
    tool = body.get("tool") or body.get("name")
    args = body.get("arguments") or body.get("params") or {}
    client = request.app.state.client
    mod = _platform(args.get("platform", "ios"))
    if tool == "search_app":
        if not mod:
            return JSONResponse(status_code=400, content={"error": "bad platform"})
        return {"results": await mod.search(client, args.get("term", ""), args.get("country", "us"))}
    if tool == "analyze_app_reviews":
        if not mod or not args.get("app_id"):
            return JSONResponse(status_code=400, content={"error": "platform + app_id required"})
        return await _analyze(client, mod, args["app_id"], args.get("country", "us"), int(args.get("pages", 5)))
    if tool == "compare_apps":
        if not mod:
            return JSONResponse(status_code=400, content={"error": "bad platform"})
        ids = args.get("app_ids", [])
        rows = await asyncio.gather(
            *[_analyze(client, mod, i, args.get("country", "us"), 3) for i in ids]
        )
        return {"apps": [{"app_id": i, "name": r["app"].get("name"),
                          "overall_rating": r.get("overall_rating"),
                          "negative_pct": r["sentiment"]["negative"]["pct"]}
                         for i, r in zip(ids, rows)]}
    return JSONResponse(
        status_code=404,
        content={"error": f"unknown tool: {tool}", "tools": [t["name"] for t in _tool_manifest()]},
    )
