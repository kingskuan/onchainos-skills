"""Whole-market breakout screener via the public TradingView scanner endpoint.

Scans the entire US market for volume-driven breakouts (big % move + unusual
volume), mirroring the BreakoutAnalysis stage-1 filters. No API key needed.
Filters are configurable per request; defaults come from FILTERS.
"""
from __future__ import annotations

from typing import Any

import httpx

SCAN_URL = "https://scanner.tradingview.com/america/scan"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Stage-1 defaults (BreakoutAnalysis config): tune per request via /scan params.
FILTERS = {
    "min_change_percent": 6.0,      # up at least X% today
    "min_volume": 1_000_000,        # shares traded
    "min_relative_volume": 2.0,     # vs 10-day average
    "min_price": 0.5,
    "max_price": 100.0,
    "min_market_cap": 200_000_000,  # non-tech micro-cap floor
    # large caps (> this) qualify at min_change_percent; smaller need the higher bar
    "large_cap_threshold": 10_000_000_000,
    "small_cap_min_change_percent": 10.0,
}

_COLUMNS = [
    "name", "close", "change", "volume", "relative_volume_10d_calc",
    "market_cap_basic", "sector", "change_from_open", "average_volume_10d_calc",
]


async def scan(client: httpx.AsyncClient, flt: dict[str, Any] | None = None, limit: int = 30) -> dict[str, Any]:
    f = {**FILTERS, **(flt or {})}
    body = {
        "filter": [
            {"left": "change", "operation": "greater", "right": f["min_change_percent"]},
            {"left": "volume", "operation": "greater", "right": f["min_volume"]},
            {"left": "relative_volume_10d_calc", "operation": "greater", "right": f["min_relative_volume"]},
            {"left": "close", "operation": "in_range", "right": [f["min_price"], f["max_price"]]},
            {"left": "market_cap_basic", "operation": "greater", "right": f["min_market_cap"]},
        ],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": _COLUMNS,
        "sort": {"sortBy": "change", "sortOrder": "desc"},
        "range": [0, max(limit * 2, 60)],
    }
    r = await client.post(SCAN_URL, json=body, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()

    rows = []
    for entry in data.get("data", []):
        d = entry.get("d", [])
        if len(d) < len(_COLUMNS):
            continue
        rec = dict(zip(_COLUMNS, d))
        mcap = rec.get("market_cap_basic") or 0
        chg = rec.get("change") or 0
        # 2-tier bar: small caps need a stronger move to count as a real breakout
        bar = (
            f["min_change_percent"]
            if mcap >= f["large_cap_threshold"]
            else f["small_cap_min_change_percent"]
        )
        if chg < bar:
            continue
        rows.append({
            "ticker": rec["name"],
            "price": round(rec["close"], 4) if rec.get("close") else None,
            "change_pct": round(chg, 2),
            "volume": int(rec["volume"]) if rec.get("volume") else None,
            "relative_volume": round(rec["relative_volume_10d_calc"], 2) if rec.get("relative_volume_10d_calc") else None,
            "market_cap": mcap,
            "sector": rec.get("sector"),
            "change_from_open_pct": round(rec["change_from_open"], 2) if rec.get("change_from_open") else None,
        })
        if len(rows) >= limit:
            break

    return {
        "scanned_market": "US",
        "filters": {k: f[k] for k in (
            "min_change_percent", "min_volume", "min_relative_volume",
            "min_price", "max_price", "min_market_cap", "small_cap_min_change_percent",
        )},
        "count": len(rows),
        "breakouts": rows,
        "note": (
            "Stage-1 volume/price breakout screen over the whole US market "
            "(TradingView). Run /analyze/{ticker} for AI context, or enable the "
            "historical-quality gate to filter weak long-term performers."
        ),
        "disclaimer": "Informational only, not investment advice.",
    }
