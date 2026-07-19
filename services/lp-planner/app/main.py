"""LP Planner — FastAPI service.

Single-side USDG LP screening + entry planner. Given a set of candidate tokens
and their recent closes, screens each one against the GMCN-style filters
(trending rank, TF-24h, market cap, volume, liquidity, pool preference,
flap.fun exclusion) and generates a WAIT / ENTER / SKIP plan around a support
band placed just below the recent low.

Endpoints
  GET  /            info + MCP manifest
  GET  /health      liveness
  GET  /run         demo screening + plans (backwards compatible with the
                    original Railway repo — same JSON shape as /)
  GET  /plans       plans only
  GET  /screened    screening results only
  POST /run         same as GET /run but with a JSON body {candidates, closes,
                    screen_cfg?, lp_cfg?} to drive from live data
  POST /plan        given one token + its closes, return a single LPPlan
  POST /mcp         MCP-style dispatch (tools: screen_and_plan, plan_token)
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import okx_payment
from .lp_strategy import (
    ScreenConfig,
    SingleSideLPConfig,
    SingleSideLPStrategy,
    TokenMetrics,
    run_screening_and_lp,
)

SERVICE_NAME = "LP Planner"
VERSION = "0.1.0"

PAY_ROUTES = {
    "GET /run": okx_payment.route("0.05"),
    "GET /plans": okx_payment.route("0.05"),
    "GET /screened": okx_payment.route("0.05"),
    "POST /run": okx_payment.route("0.1"),
    "POST /plan": okx_payment.route("0.05"),
    "POST /mcp": okx_payment.route("0.1"),
}


app = FastAPI(title=SERVICE_NAME, version=VERSION)
PAYMENTS_ON = okx_payment.install(app, PAY_ROUTES)


# ── Demo candidates (kept from the original Railway repo) ──────────────────
DEMO_CANDIDATES: list[TokenMetrics] = [
    TokenMetrics(
        symbol="ABC", name="ABC Token", gmcn_trending_rank=12, tf_24h=78.0,
        market_cap_usd=1_200_000, volume_24h_usd=2_400_000, liquidity_usd=320_000,
        current_price_usd=1.85, pool_type="v2_main", tx_share_pct=72.0, is_flap_fun=False,
    ),
    TokenMetrics(
        symbol="XYZ", name="XYZ DeFi", gmcn_trending_rank=5, tf_24h=91.0,
        market_cap_usd=3_000_000, volume_24h_usd=4_200_000, liquidity_usd=800_000,
        current_price_usd=0.42, pool_type="v2_main", tx_share_pct=85.0, is_flap_fun=False,
    ),
    TokenMetrics(
        symbol="FLAP", name="Flap Fun Token", gmcn_trending_rank=8, tf_24h=90.0,
        market_cap_usd=700_000, volume_24h_usd=1_800_000, liquidity_usd=40_000,
        current_price_usd=0.014, pool_type="v3", tx_share_pct=22.0, is_flap_fun=True,
    ),
    TokenMetrics(
        symbol="LOW", name="Low Cap Token", gmcn_trending_rank=30, tf_24h=40.0,
        market_cap_usd=200_000, volume_24h_usd=300_000, liquidity_usd=50_000,
        current_price_usd=0.005, pool_type="v2_main", tx_share_pct=60.0, is_flap_fun=False,
    ),
]

DEMO_CLOSES: dict[str, list[float]] = {
    "ABC":  [1.92, 1.90, 1.88, 1.86, 1.84, 1.83, 1.85, 1.87, 1.89, 1.88, 1.86],
    "XYZ":  [0.48, 0.46, 0.44, 0.43, 0.42, 0.41, 0.42, 0.43, 0.42],
    "FLAP": [0.016, 0.015, 0.0148, 0.0145, 0.0142, 0.0141, 0.0140],
    "LOW":  [0.006, 0.0055, 0.005, 0.0048, 0.0047, 0.0049],
}


def _compute_demo() -> dict[str, Any]:
    return run_screening_and_lp(
        candidates=DEMO_CANDIDATES,
        closes_by_symbol=DEMO_CLOSES,
        screen_cfg=ScreenConfig(),
        lp_cfg=SingleSideLPConfig(capital_usdg=1_000.0),
    )


def _screen_cfg_from(d: dict[str, Any] | None) -> ScreenConfig:
    if not d:
        return ScreenConfig()
    return ScreenConfig(**{k: v for k, v in d.items() if k in ScreenConfig.__dataclass_fields__})


def _lp_cfg_from(d: dict[str, Any] | None) -> SingleSideLPConfig:
    if not d:
        return SingleSideLPConfig()
    return SingleSideLPConfig(**{k: v for k, v in d.items() if k in SingleSideLPConfig.__dataclass_fields__})


def _token_from(d: dict[str, Any]) -> TokenMetrics:
    keep = TokenMetrics.__dataclass_fields__.keys()
    return TokenMetrics(**{k: d[k] for k in keep if k in d})


def _run_custom(body: dict[str, Any]) -> dict[str, Any]:
    candidates = [_token_from(t) for t in (body.get("candidates") or [])]
    closes = body.get("closes") or body.get("closes_by_symbol") or {}
    return run_screening_and_lp(
        candidates=candidates,
        closes_by_symbol=closes,
        screen_cfg=_screen_cfg_from(body.get("screen_cfg")),
        lp_cfg=_lp_cfg_from(body.get("lp_cfg")),
    )


def _tool_manifest() -> list[dict[str, Any]]:
    return [
        {
            "name": "screen_and_plan",
            "description": (
                "Screen a list of candidate tokens against GMCN-style filters and "
                "return a single-side USDG LP entry plan (WAIT / ENTER / SKIP) per "
                "screened-in token. Provide candidates (list of TokenMetrics) and "
                "closes (map symbol -> recent close prices). Optional screen_cfg / lp_cfg."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "candidates": {"type": "array"},
                    "closes": {"type": "object"},
                    "screen_cfg": {"type": "object"},
                    "lp_cfg": {"type": "object"},
                },
            },
        },
        {
            "name": "plan_token",
            "description": (
                "Given one TokenMetrics and its recent close prices, return an "
                "LPPlan (single-side USDG). Skips screening — use when you've "
                "already picked a token."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "token": {"type": "object"},
                    "closes": {"type": "array"},
                    "lp_cfg": {"type": "object"},
                },
                "required": ["token", "closes"],
            },
        },
        {
            "name": "demo_run",
            "description": "Run the built-in demo (four sample tokens) — same shape as GET /run.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]


@app.get("/")
async def root():
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "description": (
            "Single-side USDG LP screening + entry planner. GMCN-style token "
            "filters, support-band range, WAIT / ENTER / SKIP verdict per token."
        ),
        "endpoints": {
            "run_demo": "GET /run",
            "plans_only": "GET /plans",
            "screened_only": "GET /screened",
            "run_custom": "POST /run  {candidates,closes,screen_cfg?,lp_cfg?}",
            "plan_token": "POST /plan {token,closes,lp_cfg?}",
            "mcp": "POST /mcp",
        },
        "mcp_tools": _tool_manifest(),
        "payments": {
            "enabled": PAYMENTS_ON,
            "scheme": "x402 (exact) via OKX facilitator",
            "network": os.getenv("PAY_NETWORK", "eip155:196"),
            "prices": {
                "run": "$0.05", "plans": "$0.05", "screened": "$0.05",
                "run_custom": "$0.10", "plan_token": "$0.05", "mcp": "$0.10",
            },
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/run")
async def run_demo_get():
    return _compute_demo()


@app.get("/plans")
async def plans_only():
    return {"plans": _compute_demo()["plans"]}


@app.get("/screened")
async def screened_only():
    return {"screened": _compute_demo()["screened"]}


@app.post("/run")
async def run_custom(body: dict[str, Any]):
    try:
        return _run_custom(body)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"error": str(e)[:200]})


@app.post("/plan")
async def plan_one(body: dict[str, Any]):
    try:
        token = _token_from(body["token"])
        closes = body["closes"]
        lp = SingleSideLPStrategy(_lp_cfg_from(body.get("lp_cfg")))
        from dataclasses import asdict
        return asdict(lp.plan(token, closes))
    except KeyError as e:
        return JSONResponse(status_code=400, content={"error": f"missing field: {e.args[0]}"})
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"error": str(e)[:200]})


@app.post("/mcp")
async def mcp_endpoint(request: Request, body: dict[str, Any]):
    tool = body.get("tool") or body.get("name")
    args = body.get("arguments") or body.get("params") or {}
    if tool == "demo_run":
        return _compute_demo()
    if tool == "screen_and_plan":
        return _run_custom(args)
    if tool == "plan_token":
        if "token" not in args or "closes" not in args:
            return JSONResponse(status_code=400, content={"error": "token and closes required"})
        from dataclasses import asdict
        lp = SingleSideLPStrategy(_lp_cfg_from(args.get("lp_cfg")))
        return asdict(lp.plan(_token_from(args["token"]), args["closes"]))
    return JSONResponse(
        status_code=404,
        content={"error": f"unknown tool: {tool}", "tools": [t["name"] for t in _tool_manifest()]},
    )
