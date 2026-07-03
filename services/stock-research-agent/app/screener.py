"""Finviz-lite screener.

Free data has no ready-made screening universe, so this filters a curated
universe (default: large-cap US names, overridable via `tickers`) on metrics
computed from EDGAR + Yahoo. It is intentionally smaller-scale than Finviz —
the deep-research endpoint is the core value; this narrows a watchlist.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from . import edgar, yahoo
from .research import _cagr, _safe_div

# Curated default universe (mega/large-cap, sector-diverse). Override with
# ?tickers=... to screen any set.
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD",
    "JPM", "V", "MA", "UNH", "JNJ", "LLY", "XOM", "CVX", "KO", "PEP", "PG",
    "COST", "WMT", "HD", "MCD", "NFLX", "CRM", "ORCL", "ADBE", "CSCO", "INTC",
]


async def quick_metrics(client: httpx.AsyncClient, ticker: str) -> dict[str, Any] | None:
    """Compact metric set for screening (no analyst call — keeps it fast)."""
    ref = await edgar.resolve_cik(client, ticker)
    if not ref:
        return None
    try:
        facts = await edgar.company_facts(client, ref["cik"])
    except Exception:  # noqa: BLE001
        return None
    rev = edgar.series_for(facts, "revenue")
    ni = edgar.series_for(facts, "net_income")
    eq = edgar.latest(edgar.series_for(facts, "equity"))
    shares = edgar.latest_shares_outstanding(facts)
    try:
        px = await yahoo.price(client, ticker)
        price = px.get("price")
    except Exception:  # noqa: BLE001
        price = None
    rev_l = edgar.latest(rev)
    ni_l = edgar.latest(ni)
    mkt_cap = (price * shares) if (price and shares) else None
    eps = _safe_div(ni_l, shares)
    return {
        "ticker": ticker,
        "company": ref["title"],
        "price": price,
        "market_cap": mkt_cap,
        "pe": _safe_div(price, eps),
        "ps": _safe_div(mkt_cap, rev_l),
        "pb": _safe_div(mkt_cap, eq),
        "net_margin": _safe_div(ni_l, rev_l),
        "revenue_cagr_5y": _cagr({y: rev[y] for y in sorted(rev)[-5:]}) if rev else None,
    }


def _passes(m: dict[str, Any], flt: dict[str, float]) -> bool:
    def ge(key, val):
        return m.get(key) is not None and m[key] >= val

    def le(key, val):
        return m.get(key) is not None and m[key] <= val

    if "min_market_cap" in flt and not ge("market_cap", flt["min_market_cap"]):
        return False
    if "max_market_cap" in flt and not le("market_cap", flt["max_market_cap"]):
        return False
    if "max_pe" in flt and not le("pe", flt["max_pe"]):
        return False
    if "min_pe" in flt and not ge("pe", flt["min_pe"]):
        return False
    if "max_ps" in flt and not le("ps", flt["max_ps"]):
        return False
    if "min_net_margin" in flt and not ge("net_margin", flt["min_net_margin"]):
        return False
    if "min_revenue_cagr" in flt and not ge("revenue_cagr_5y", flt["min_revenue_cagr"]):
        return False
    return True


async def screen(
    client: httpx.AsyncClient,
    universe: list[str],
    flt: dict[str, float],
    limit: int = 25,
) -> dict[str, Any]:
    sem = asyncio.Semaphore(6)

    async def one(t: str):
        async with sem:
            try:
                return await quick_metrics(client, t)
            except Exception:  # noqa: BLE001
                return None

    rows = [r for r in await asyncio.gather(*[one(t) for t in universe]) if r]
    matches = [r for r in rows if _passes(r, flt)]
    # sort by revenue growth desc, then market cap desc
    matches.sort(
        key=lambda r: (
            r.get("revenue_cagr_5y") or -1,
            r.get("market_cap") or -1,
        ),
        reverse=True,
    )
    return {
        "filters": flt,
        "universe_size": len(universe),
        "evaluated": len(rows),
        "match_count": len(matches),
        "matches": matches[:limit],
        "note": (
            "Screens a curated universe (pass ?tickers=A,B,C to customize). "
            "For a full-market screen, supply your own universe."
        ),
    }
