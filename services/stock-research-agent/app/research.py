"""Deep single-stock research assembler.

Combines SEC EDGAR fundamentals with Yahoo price/analyst data into one
structured report modelled on the "study a single stock end-to-end" workflow:
is revenue/profit growing, what's the valuation, what's the blow-up risk, and
what do analysts think.
"""
from __future__ import annotations

from typing import Any

import httpx

from . import edgar, yahoo
from .segments import segments as fetch_segments


def _safe_div(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return a / b
    except Exception:  # noqa: BLE001
        return None


def _cagr(series: dict[int, float]) -> float | None:
    if len(series) < 2:
        return None
    years = sorted(series)
    first, last = series[years[0]], series[years[-1]]
    n = years[-1] - years[0]
    if first is None or last is None or first <= 0 or n <= 0:
        return None
    try:
        return (last / first) ** (1 / n) - 1
    except Exception:  # noqa: BLE001
        return None


def _last5(series: dict[int, float]) -> dict[str, float]:
    years = sorted(series)[-5:]
    return {str(y): series[y] for y in years}


def _yoy(series: dict[int, float]) -> dict[str, float | None]:
    years = sorted(series)[-5:]
    out: dict[str, float | None] = {}
    for i, y in enumerate(years):
        if i == 0:
            out[str(y)] = None
        else:
            prev = series[years[i - 1]]
            out[str(y)] = _safe_div(series[y] - prev, abs(prev)) if prev else None
    return out


def _health(f: dict, mkt_cap: float | None) -> dict[str, Any]:
    """Financial-health scorecard: ratios, Altman Z, and an A–F grade."""
    ca = edgar.latest(edgar.series_for(f, "current_assets"))
    cl = edgar.latest(edgar.series_for(f, "current_liabilities"))
    ta = edgar.latest(edgar.series_for(f, "assets"))
    tl = edgar.latest(edgar.series_for(f, "liabilities"))
    eq = edgar.latest(edgar.series_for(f, "equity"))
    re = edgar.latest(edgar.series_for(f, "retained_earnings"))
    ebit = edgar.latest(edgar.series_for(f, "operating_income"))
    rev = edgar.latest(edgar.series_for(f, "revenue"))
    ni = edgar.latest(edgar.series_for(f, "net_income"))
    ocf = edgar.latest(edgar.series_for(f, "operating_cash_flow"))
    ltd = edgar.latest(edgar.series_for(f, "long_term_debt")) or 0
    std = edgar.latest(edgar.series_for(f, "short_term_debt")) or 0
    total_debt = ltd + std

    current_ratio = _safe_div(ca, cl)
    debt_to_equity = _safe_div(total_debt, eq)
    net_margin = _safe_div(ni, rev)
    working_capital = (ca - cl) if (ca is not None and cl is not None) else None

    # Altman Z-score (classic manufacturing model)
    z = None
    if ta and ta > 0 and tl and mkt_cap:
        try:
            z = (
                1.2 * _safe_div(working_capital, ta)
                + 1.4 * _safe_div(re, ta)
                + 3.3 * _safe_div(ebit, ta)
                + 0.6 * _safe_div(mkt_cap, tl)
                + 1.0 * _safe_div(rev, ta)
            )
        except Exception:  # noqa: BLE001
            z = None

    # simple weighted grade
    score = 0
    checks = 0

    def add(cond: bool | None):
        nonlocal score, checks
        if cond is None:
            return
        checks += 1
        if cond:
            score += 1

    add(current_ratio is not None and current_ratio >= 1.5)
    add(debt_to_equity is not None and debt_to_equity < 1.0)
    add(net_margin is not None and net_margin > 0.05)
    add(ni is not None and ni > 0)
    add(ocf is not None and ocf > 0)
    add(z is not None and z > 2.99)
    pct = _safe_div(score, checks)
    grade = None
    if pct is not None:
        grade = (
            "A" if pct >= 0.85 else
            "B" if pct >= 0.65 else
            "C" if pct >= 0.45 else
            "D" if pct >= 0.25 else "F"
        )

    z_zone = None
    if z is not None:
        z_zone = "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"

    return {
        "grade": grade,
        "score": f"{score}/{checks}" if checks else None,
        "current_ratio": current_ratio,
        "debt_to_equity": debt_to_equity,
        "net_margin": net_margin,
        "operating_cash_flow_positive": (ocf is not None and ocf > 0),
        "altman_z": z,
        "altman_zone": z_zone,
    }


async def research(client: httpx.AsyncClient, ticker: str) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    ref = await edgar.resolve_cik(client, ticker)
    if not ref:
        return {
            "ticker": ticker,
            "error": "not_found",
            "message": (
                "Ticker not found in SEC EDGAR (US-listed filers only in this "
                "version). Non-US tickers are on the roadmap."
            ),
        }
    facts = await edgar.company_facts(client, ref["cik"])

    rev = edgar.series_for(facts, "revenue")
    gp = edgar.series_for(facts, "gross_profit")
    oi = edgar.series_for(facts, "operating_income")
    ni = edgar.series_for(facts, "net_income")
    ocf = edgar.series_for(facts, "operating_cash_flow")
    capex = edgar.series_for(facts, "capex")
    assets = edgar.series_for(facts, "assets")
    equity = edgar.series_for(facts, "equity")
    da = edgar.series_for(facts, "dep_amort")

    shares = edgar.latest_shares_outstanding(facts)

    # price / valuation (best effort — degrade if Yahoo is unreachable)
    px: dict[str, Any] = {}
    try:
        px = await yahoo.price(client, ticker)
    except Exception as e:  # noqa: BLE001
        px = {"price": None, "error": str(e)[:120]}
    price = px.get("price")
    mkt_cap = (price * shares) if (price and shares) else None

    rev_l = edgar.latest(rev)
    ni_l = edgar.latest(ni)
    eq_l = edgar.latest(equity)
    oi_l = edgar.latest(oi)
    da_l = edgar.latest(da) or 0
    ltd = edgar.latest(edgar.series_for(facts, "long_term_debt")) or 0
    std = edgar.latest(edgar.series_for(facts, "short_term_debt")) or 0
    cash = edgar.latest(edgar.series_for(facts, "cash")) or 0
    ev = (mkt_cap + ltd + std - cash) if mkt_cap is not None else None
    ebitda = (oi_l + da_l) if oi_l is not None else None
    eps = _safe_div(ni_l, shares)

    valuation = {
        "market_cap": mkt_cap,
        "enterprise_value": ev,
        "pe": _safe_div(price, eps),
        "ps": _safe_div(mkt_cap, rev_l),
        "pb": _safe_div(mkt_cap, eq_l),
        "ev_ebitda": _safe_div(ev, ebitda),
        "eps_ttm_proxy": eps,
    }

    analyst = await yahoo.analyst(client, ticker)

    # per-product / per-geography revenue (best-effort; never breaks research)
    try:
        seg = await fetch_segments(client, ref["cik"])
    except Exception as e:  # noqa: BLE001
        seg = {"available": False, "reason": str(e)[:120]}

    # narrative flags for the "5 things to check" workflow
    rev_cagr = _cagr({y: rev[y] for y in sorted(rev)[-5:]}) if rev else None
    ni_cagr = _cagr({y: ni[y] for y in sorted(ni)[-5:]}) if ni else None
    signals = {
        "revenue_growing": bool(rev_cagr and rev_cagr > 0),
        "revenue_cagr_5y": rev_cagr,
        "earnings_growing": bool(ni_cagr and ni_cagr > 0),
        "earnings_cagr_5y": ni_cagr,
    }

    return {
        "ticker": ticker,
        "company": ref["title"],
        "cik": ref["cik"],
        "quote": px,
        "shares_outstanding": shares,
        "financials": {
            "revenue": _last5(rev),
            "revenue_yoy": _yoy(rev),
            "gross_profit": _last5(gp),
            "operating_income": _last5(oi),
            "net_income": _last5(ni),
            "net_income_yoy": _yoy(ni),
            "operating_cash_flow": _last5(ocf),
            "capex": _last5(capex),
            "total_assets": _last5(assets),
            "equity": _last5(equity),
        },
        "growth": signals,
        "valuation": valuation,
        "financial_health": _health(facts, mkt_cap),
        "analysts": analyst,
        "segments": seg,
        "data_sources": ["SEC EDGAR companyfacts", "Yahoo Finance v8/v10"],
        "disclaimer": (
            "Informational only, not investment advice. Data from public "
            "filings and Yahoo Finance; verify before acting."
        ),
    }
