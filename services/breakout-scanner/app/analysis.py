"""Historical-quality gate (Yahoo, replaces Alpaca), AI breakout analysis with
news, and the market briefing.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from . import llm

UA = {"User-Agent": "Mozilla/5.0 (compatible; breakout-scanner/0.1)"}

INDEXES = {"^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "Dow Jones", "^VIX": "VIX"}


async def _chart(client: httpx.AsyncClient, symbol: str, rng: str = "1y", interval: str = "1d") -> dict[str, Any]:
    r = await client.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"range": rng, "interval": interval},
        headers=UA,
        timeout=25,
    )
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    meta = res.get("meta", {})
    return {"closes": closes, "price": meta.get("regularMarketPrice"),
            "prev_close": meta.get("chartPreviousClose")}


async def quality_gate(client: httpx.AsyncClient, ticker: str) -> dict[str, Any]:
    """Filter out chronic weak performers. Pass if the stock has real long-term
    strength: positive ~1y return OR trading in the upper half of its 1y range."""
    try:
        h = await _chart(client, ticker, "1y")
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": str(e)[:100], "pass": True}  # don't block on data error
    closes = h["closes"]
    if len(closes) < 30:
        return {"available": False, "pass": True}
    price = h["price"] or closes[-1]
    lo, hi = min(closes), max(closes)
    one_year_return = (price / closes[0] - 1) if closes[0] else None
    pct_of_range = (price - lo) / (hi - lo) if hi > lo else None
    ok = bool((one_year_return is not None and one_year_return > 0)
              or (pct_of_range is not None and pct_of_range >= 0.5))
    return {
        "available": True,
        "pass": ok,
        "one_year_return": round(one_year_return, 3) if one_year_return is not None else None,
        "pct_of_52w_range": round(pct_of_range, 2) if pct_of_range is not None else None,
    }


async def _news(client: httpx.AsyncClient, ticker: str, n: int = 5) -> list[str]:
    try:
        r = await client.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": ticker, "newsCount": n, "quotesCount": 0},
            headers=UA, timeout=20,
        )
        items = r.json().get("news", [])
        return [it.get("title", "") for it in items[:n] if it.get("title")]
    except Exception:  # noqa: BLE001
        return []


async def analyze_breakout(client: httpx.AsyncClient, ticker: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
    ticker = ticker.upper()
    q, headlines = await asyncio.gather(quality_gate(client, ticker), _news(client, ticker))
    ctx = [f"Ticker: {ticker}"]
    if row:
        ctx.append(
            f"Today: {row.get('change_pct')}% on {row.get('volume')} shares, "
            f"relative volume {row.get('relative_volume')}x, price ${row.get('price')}, "
            f"sector {row.get('sector')}"
        )
    if q.get("available"):
        ctx.append(f"1y return {q.get('one_year_return')}, at {q.get('pct_of_52w_range')} of 52w range")
    if headlines:
        ctx.append("Recent headlines:\n- " + "\n- ".join(headlines))
    context = "\n".join(ctx)

    if not llm.configured():
        return {"ticker": ticker, "quality": q, "headlines": headlines,
                "analysis": None, "reason": "LLM not configured (set LLM_API_KEY)", "grounding": context}

    analysis = await llm.chat(client, [
        {"role": "system", "content": (
            "You are a markets analyst. In plain English, explain why this stock is "
            "moving today, what likely drove it (tie to the headlines if relevant), key "
            "levels/things to watch, and the main risk. Be concrete, ~120 words. "
            "Not investment advice; do not invent facts beyond the data."
        )},
        {"role": "user", "content": context},
    ])
    return {
        "ticker": ticker,
        "quality": q,
        "headlines": headlines,
        "analysis": analysis.strip(),
        "model": llm.config()["model"],
        "disclaimer": "Informational only, not investment advice.",
    }


async def briefing(client: httpx.AsyncClient) -> dict[str, Any]:
    async def one(sym: str, name: str):
        try:
            h = await _chart(client, sym, "5d")
            price, prev = h["price"], h["prev_close"]
            chg = (price / prev - 1) * 100 if price and prev else None
            return {"index": name, "level": round(price, 2) if price else None,
                    "change_pct": round(chg, 2) if chg is not None else None}
        except Exception:  # noqa: BLE001
            return {"index": name, "level": None, "change_pct": None}

    idx = await asyncio.gather(*[one(s, n) for s, n in INDEXES.items()])
    summary = None
    if llm.configured():
        snap = "; ".join(f"{i['index']} {i['level']} ({i['change_pct']}%)" for i in idx)
        try:
            summary = (await llm.chat(client, [
                {"role": "system", "content": "You write a tight market briefing (~90 words)."},
                {"role": "user", "content": (
                    f"Index snapshot: {snap}. Write a plain-English briefing: overall tone, "
                    "what the VIX implies, and a reminder to watch scheduled events "
                    "(Fed, CPI, major earnings). Not investment advice."
                )},
            ])).strip()
        except Exception:  # noqa: BLE001
            summary = None
    return {"indices": idx, "summary": summary,
            "disclaimer": "Informational only, not investment advice."}
