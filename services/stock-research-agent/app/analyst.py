"""AI analyst layer — a lightweight multi-agent debate grounded on our own
structured data (financials, valuation, health, segments, analyst targets).

Inspired by the TradingAgents pattern (bull vs bear → judge) but compact and
cost-controlled: 2 parallel debate calls + 1 judge call, all fed the same
grounded context. The moat is the grounding — the model reasons over our
EDGAR-derived facts, not generic web text.

Research support only, not investment advice.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from . import llm
from .research import research


def _fmt_money(v) -> str:
    if not isinstance(v, (int, float)):
        return "n/a"
    a = abs(v)
    if a >= 1e12:
        return f"${v/1e12:.2f}T"
    if a >= 1e9:
        return f"${v/1e9:.2f}B"
    if a >= 1e6:
        return f"${v/1e6:.2f}M"
    return f"${v:.2f}"


def _pct(v) -> str:
    return f"{v*100:.1f}%" if isinstance(v, (int, float)) else "n/a"


def build_context(d: dict[str, Any]) -> str:
    """Compact, factual grounding text from a /research payload."""
    fin = d.get("financials", {})
    val = d.get("valuation", {})
    health = d.get("financial_health", {})
    growth = d.get("growth", {})
    an = d.get("analysts", {})
    seg = d.get("segments", {})
    lines = [
        f"Company: {d.get('company')} ({d.get('ticker')})",
        f"Price: {d.get('quote',{}).get('price')}  52w: "
        f"{d.get('quote',{}).get('fifty_two_week_low')}–{d.get('quote',{}).get('fifty_two_week_high')}",
        f"Revenue (5y): {fin.get('revenue')}",
        f"Net income (5y): {fin.get('net_income')}",
        f"Revenue CAGR 5y: {_pct(growth.get('revenue_cagr_5y'))}, "
        f"Earnings CAGR 5y: {_pct(growth.get('earnings_cagr_5y'))}",
        f"Valuation: P/E {val.get('pe')}, P/S {val.get('ps')}, P/B {val.get('pb')}, "
        f"EV/EBITDA {val.get('ev_ebitda')}, mktcap {_fmt_money(val.get('market_cap'))}",
        f"Health: grade {health.get('grade')} ({health.get('score')}), "
        f"current ratio {health.get('current_ratio')}, D/E {health.get('debt_to_equity')}, "
        f"net margin {_pct(health.get('net_margin'))}, Altman Z {health.get('altman_z')} "
        f"({health.get('altman_zone')})",
    ]
    if an.get("available"):
        lines.append(
            f"Analysts: target mean {an.get('target_mean')} (low {an.get('target_low')} / "
            f"high {an.get('target_high')}), {an.get('num_analysts')} analysts, "
            f"rec {an.get('recommendation')}"
        )
    if seg.get("available"):
        def _latest_year(series: dict) -> Any:
            return series[max(series)] if series else None

        prod = seg.get("by_product_or_service") or {}
        if prod:
            lines.append("Revenue by product/service (latest FY): " + ", ".join(
                f"{k} {_fmt_money(_latest_year(v))}" for k, v in prod.items()))
        geo = seg.get("by_reportable_segment") or seg.get("by_geography") or {}
        if geo:
            lines.append("Revenue by segment/geography (latest FY): " + ", ".join(
                f"{k} {_fmt_money(_latest_year(v))}" for k, v in geo.items()))
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


async def analyze_stock(client: httpx.AsyncClient, ticker: str) -> dict[str, Any]:
    data = await research(client, ticker)
    if data.get("error"):
        return {"ticker": ticker, "available": False, "reason": data.get("message", "not found")}
    if not llm.configured():
        return {
            "ticker": ticker.upper(),
            "available": False,
            "reason": "AI analyst not configured — set LLM_API_KEY (OpenAI-compatible).",
            "grounding": build_context(data),
        }

    ctx = build_context(data)
    sys_common = (
        "You are an equity analyst. Reason ONLY from the provided factual data. "
        "Be specific and cite numbers. Do not invent data. This is research "
        "support, not investment advice."
    )

    async def bull() -> str:
        return await llm.chat(client, [
            {"role": "system", "content": sys_common},
            {"role": "user", "content": f"DATA:\n{ctx}\n\nMake the strongest BULL case in 4-6 bullet points."},
        ])

    async def bear() -> str:
        return await llm.chat(client, [
            {"role": "system", "content": sys_common},
            {"role": "user", "content": f"DATA:\n{ctx}\n\nMake the strongest BEAR case in 4-6 bullet points."},
        ])

    bull_case, bear_case = await asyncio.gather(bull(), bear())

    judge = await llm.chat(client, [
        {"role": "system", "content": sys_common},
        {"role": "user", "content": (
            f"DATA:\n{ctx}\n\nBULL:\n{bull_case}\n\nBEAR:\n{bear_case}\n\n"
            "Weigh both sides and return ONLY JSON with keys: "
            "rating (one of STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL), "
            "confidence (0-1), thesis (2-3 sentences), "
            "key_reasons (array of strings), key_risks (array of strings), "
            "what_would_change_my_mind (string)."
        )},
    ], temperature=0.2)

    verdict = _extract_json(judge) or {"rating": "HOLD", "raw": judge}
    return {
        "ticker": data.get("ticker"),
        "company": data.get("company"),
        "available": True,
        "verdict": verdict,
        "debate": {"bull_case": bull_case, "bear_case": bear_case},
        "grounding": ctx,
        "model": llm.config()["model"],
        "disclaimer": "AI-generated research opinion grounded on public filings. Not investment advice.",
    }
