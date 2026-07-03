"""Yahoo Finance client (free, no key).

The public v8 chart endpoint (price + history) is open. The v10 quoteSummary
endpoint (analyst targets, key stats) needs a cookie+crumb handshake and may be
rate-limited from some hosts — so it is treated as a best-effort enhancement:
if it fails we degrade gracefully and the research payload flags it.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA}

_crumb: tuple[float, str, dict] | None = None  # (ts, crumb, cookies)


async def price(client: httpx.AsyncClient, ticker: str) -> dict[str, Any]:
    """Current price + basic meta from the open v8 chart endpoint."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    r = await client.get(
        url, headers=HEADERS, params={"range": "1y", "interval": "1d"}, timeout=25
    )
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    meta = result["meta"]
    closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
    hi_52 = max(closes) if closes else None
    lo_52 = min(closes) if closes else None
    return {
        "price": meta.get("regularMarketPrice"),
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "prev_close": meta.get("chartPreviousClose"),
        "fifty_two_week_high": hi_52,
        "fifty_two_week_low": lo_52,
    }


async def _ensure_crumb(client: httpx.AsyncClient) -> tuple[str, dict] | None:
    global _crumb
    if _crumb and (time.time() - _crumb[0]) < 1800:
        return _crumb[1], _crumb[2]
    try:
        # prime cookies
        r0 = await client.get(
            "https://fc.yahoo.com", headers=HEADERS, timeout=15
        )
        cookies = dict(r0.cookies)
        r1 = await client.get(
            "https://query1.finance.yahoo.com/v1/test/getcrumb",
            headers=HEADERS,
            cookies=cookies,
            timeout=15,
        )
        crumb = r1.text.strip()
        if crumb and "<" not in crumb:
            _crumb = (time.time(), crumb, cookies)
            return crumb, cookies
    except Exception:
        return None
    return None


async def analyst(client: httpx.AsyncClient, ticker: str) -> dict[str, Any]:
    """Best-effort analyst targets / recommendation / forward estimates.

    Returns {"available": False, "reason": ...} when the crumb-gated endpoint
    is unreachable, so callers can render a clean degraded state.
    """
    got = await _ensure_crumb(client)
    if not got:
        return {"available": False, "reason": "quoteSummary crumb unavailable"}
    crumb, cookies = got
    modules = "financialData,recommendationTrend,priceTargetSummary,earningsTrend"
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    try:
        r = await client.get(
            url,
            headers=HEADERS,
            cookies=cookies,
            params={"modules": modules, "crumb": crumb},
            timeout=25,
        )
        if r.status_code != 200:
            return {"available": False, "reason": f"http {r.status_code}"}
        res = r.json()["quoteSummary"]["result"][0]
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": str(e)[:120]}

    fin = res.get("financialData", {})
    pts = res.get("priceTargetSummary", {})

    def raw(d, k):
        v = d.get(k)
        return v.get("raw") if isinstance(v, dict) else v

    # forward estimates from earningsTrend (+1y revenue/eps growth)
    est: dict[str, Any] = {}
    for t in res.get("earningsTrend", {}).get("trend", []):
        if t.get("period") in ("+1y", "0y"):
            est[t["period"]] = {
                "revenue_estimate": raw(t.get("revenueEstimate", {}), "avg"),
                "eps_estimate": raw(t.get("earningsEstimate", {}), "avg"),
                "growth": raw(t, "growth"),
            }

    return {
        "available": True,
        "target_mean": raw(fin, "targetMeanPrice"),
        "target_high": raw(fin, "targetHighPrice") or raw(pts, "targetHigh"),
        "target_low": raw(fin, "targetLowPrice") or raw(pts, "targetLow"),
        "num_analysts": raw(fin, "numberOfAnalystOpinions"),
        "recommendation": fin.get("recommendationKey"),
        "recommendation_mean": raw(fin, "recommendationMean"),
        "forward_estimates": est,
    }
