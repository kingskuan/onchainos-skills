"""Crypto intel via the public DexScreener API (free, no key).

Reimplements the *ideas* behind the Hermes skill-packs (defi-security-scanner +
crypto-arb) from public data: a token safety heuristic and a cross-venue price
spread. Read-only, heuristic, informational — not financial advice, and not the
original packs' code.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

UA = {"User-Agent": "crypto-intel/0.1", "Accept": "application/json"}
BASE = "https://api.dexscreener.com/latest/dex"


async def _get(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    r = await client.get(f"{BASE}{path}", headers=UA, timeout=25)
    r.raise_for_status()
    return r.json()


def top_symbol(pairs: list) -> str | None:
    for p in pairs:
        s = p.get("baseToken", {}).get("symbol")
        if s:
            return s
    return None


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


async def token_safety(client: httpx.AsyncClient, address: str, chain: str | None = None) -> dict[str, Any]:
    data = await _get(client, f"/tokens/{address}")
    pairs = data.get("pairs") or []
    if chain:
        pairs = [p for p in pairs if (p.get("chainId") or "").lower() == chain.lower()]
    if not pairs:
        return {"address": address, "found": False,
                "message": "No DEX pairs found for this token/chain."}

    # use the deepest-liquidity pair as the reference
    pairs.sort(key=lambda p: _num(p.get("liquidity", {}).get("usd")), reverse=True)
    top = pairs[0]
    liq = _num(top.get("liquidity", {}).get("usd"))
    total_liq = sum(_num(p.get("liquidity", {}).get("usd")) for p in pairs)
    txns = top.get("txns", {}).get("h24", {}) or {}
    buys, sells = int(txns.get("buys", 0)), int(txns.get("sells", 0))
    created = top.get("pairCreatedAt")
    age_days = ((time.time() * 1000 - created) / 86_400_000) if created else None
    vol24 = _num(top.get("volume", {}).get("h24"))
    fdv = _num(top.get("fdv"))
    price_change = top.get("priceChange", {}) or {}

    flags: list[str] = []
    # honeypot signal: lots of buys, almost no sells → can't sell
    if buys >= 25 and sells <= max(1, buys * 0.05):
        flags.append("honeypot_signal: many buys but almost no sells")
    if total_liq < 10_000:
        flags.append("very_low_liquidity (<$10k)")
    elif total_liq < 50_000:
        flags.append("low_liquidity (<$50k)")
    if age_days is not None and age_days < 3:
        flags.append("very_new_pair (<3 days)")
    if len(pairs) == 1 and total_liq < 100_000:
        flags.append("single_thin_pair")
    if fdv and total_liq and fdv / total_liq > 200:
        flags.append("fdv_vastly_exceeds_liquidity (thin float / dump risk)")
    if abs(_num(price_change.get("h24"))) > 60:
        flags.append("extreme_24h_volatility")

    # 0-100, higher = safer
    penalty = {
        "honeypot_signal": 45, "very_low_liquidity": 30, "low_liquidity": 15,
        "very_new_pair": 20, "single_thin_pair": 12,
        "fdv_vastly_exceeds_liquidity": 15, "extreme_24h_volatility": 10,
    }
    score = 100
    for f in flags:
        key = f.split(":")[0].split(" ")[0]
        score -= penalty.get(key, 10)
    score = max(0, score)
    verdict = "high risk" if score < 40 else "caution" if score < 70 else "lower risk"

    return {
        "address": address,
        "found": True,
        "symbol": top.get("baseToken", {}).get("symbol"),
        "name": top.get("baseToken", {}).get("name"),
        "chain": top.get("chainId"),
        "price_usd": top.get("priceUsd"),
        "safety_score": score,
        "verdict": verdict,
        "flags": flags or ["no major red flags in these heuristics"],
        "signals": {
            "total_liquidity_usd": round(total_liq),
            "top_pair_liquidity_usd": round(liq),
            "pairs": len(pairs),
            "txns_24h": {"buys": buys, "sells": sells},
            "volume_24h_usd": round(vol24),
            "pair_age_days": round(age_days, 1) if age_days is not None else None,
            "fdv_usd": round(fdv) if fdv else None,
            "price_change_24h_pct": _num(price_change.get("h24")),
        },
        "disclaimer": (
            "Heuristic risk signals from public DEX data — NOT a guarantee of "
            "safety and not financial advice. Always DYOR."
        ),
    }


def _looks_like_address(q: str) -> bool:
    q = q.strip()
    return (q.startswith("0x") and len(q) >= 40) or (len(q) >= 32 and " " not in q and q.isalnum())


async def spread(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    query = query.strip()
    # Resolve to ONE token address so we compare the SAME token across venues —
    # a symbol like "PEPE" matches many different copycat tokens, which is why a
    # naive symbol search produces nonsense spreads.
    address = query
    if not _looks_like_address(query):
        s = await _get(client, f"/search?q={query}")
        cands = [p for p in (s.get("pairs") or []) if p.get("baseToken", {}).get("address")]
        if not cands:
            return {"query": query, "message": "Token not found."}
        cands.sort(key=lambda p: _num(p.get("liquidity", {}).get("usd")), reverse=True)
        address = cands[0]["baseToken"]["address"]

    data = await _get(client, f"/tokens/{address}")
    pairs = [p for p in (data.get("pairs") or []) if _num(p.get("liquidity", {}).get("usd")) > 20_000
             and p.get("priceUsd")]
    if len(pairs) < 2:
        return {"query": query, "resolved_address": address,
                "message": "Not enough liquid venues for this token to compute a spread."}
    pairs.sort(key=lambda p: _num(p.get("priceUsd")))
    lo, hi = pairs[0], pairs[-1]
    lo_p, hi_p = _num(lo.get("priceUsd")), _num(hi.get("priceUsd"))
    spread_pct = ((hi_p - lo_p) / lo_p * 100) if lo_p else None
    venues = [{
        "chain": p.get("chainId"), "dex": p.get("dexId"),
        "symbol": p.get("baseToken", {}).get("symbol"),
        "price_usd": p.get("priceUsd"),
        "liquidity_usd": round(_num(p.get("liquidity", {}).get("usd"))),
    } for p in pairs[:12]]
    return {
        "query": query,
        "resolved_address": address,
        "symbol": top_symbol(pairs),
        "venue_count": len(pairs),
        "max_spread_pct": round(spread_pct, 3) if spread_pct is not None else None,
        "cheapest": {"dex": lo.get("dexId"), "chain": lo.get("chainId"), "price_usd": lo.get("priceUsd")},
        "priciest": {"dex": hi.get("dexId"), "chain": hi.get("chainId"), "price_usd": hi.get("priceUsd")},
        "venues": venues,
        "disclaimer": (
            "Cross-venue price differences from public DEX data. Spreads may not "
            "be capturable after fees, gas, slippage, and bridge time. Not advice."
        ),
    }
