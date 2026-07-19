"""Free public DeFi data sources (no API key) — mirrors the data layer of the
DeFi Dashboard: Blockscout v2 (wallet balances), Pendle API v2 (YT/PT markets),
DeFiLlama Yields (pools). Stdlib only.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

UA = {"User-Agent": "ytos-asp/1.0", "Accept": "application/json"}

# Blockscout v2 instances per chain (all free, public).
BLOCKSCOUT = {
    "eth": "https://eth.blockscout.com", "ethereum": "https://eth.blockscout.com",
    "base": "https://base.blockscout.com", "optimism": "https://optimism.blockscout.com",
    "arbitrum": "https://arbitrum.blockscout.com", "gnosis": "https://gnosis.blockscout.com",
    "polygon": "https://polygon.blockscout.com",
}
PENDLE_BASE = "https://api-v2.pendle.finance/core"
LLAMA_POOLS = "https://yields.llama.fi/pools"

CHAIN_IDS = {"eth": 1, "ethereum": 1, "base": 8453, "optimism": 10,
             "arbitrum": 42161, "polygon": 137, "bsc": 56}

# DeFiLlama Yields uses display chain names ("Ethereum", "Base", …); map aliases.
LLAMA_CHAIN = {
    "eth": "Ethereum", "ethereum": "Ethereum", "base": "Base",
    "optimism": "Optimism", "arbitrum": "Arbitrum", "polygon": "Polygon",
    "gnosis": "Gnosis", "bsc": "BSC", "bnb": "BSC",
}


def _get(url: str, timeout: int = 25) -> Any:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode("utf-8")
    return json.loads(txt) if txt.strip() else {}


def _num(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ------------------------------- wallet --------------------------------------
def wallet_portfolio(address: str, chain: str = "eth", limit: int = 25) -> Dict[str, Any]:
    base = BLOCKSCOUT.get(chain.lower(), BLOCKSCOUT["eth"])
    addr = address.lower()
    out: Dict[str, Any] = {"address": address, "chain": chain.lower()}

    # native coin
    try:
        a = _get(f"{base}/api/v2/addresses/{addr}")
        wei = _num(a.get("coin_balance"))
        rate = _num(a.get("exchange_rate"))
        native_amt = wei / 1e18
        out["native"] = {"symbol": "ETH", "amount": round(native_amt, 6),
                         "usd": round(native_amt * rate, 2) if rate else None}
    except Exception as e:  # noqa: BLE001
        out["native"] = {"error": str(e)[:120]}

    # ERC-20 balances
    tokens: List[Dict[str, Any]] = []
    try:
        tb = _get(f"{base}/api/v2/addresses/{addr}/token-balances")
        rows = tb if isinstance(tb, list) else tb.get("items", [])
        for row in rows:
            tok = row.get("token") or {}
            dec = int(_num(tok.get("decimals"), 18)) or 18
            amt = _num(row.get("value")) / (10 ** dec)
            rate = _num(tok.get("exchange_rate"))
            usd = amt * rate if rate else None
            tokens.append({
                "symbol": tok.get("symbol"), "name": tok.get("name"),
                "address": tok.get("address"), "amount": round(amt, 6),
                "usd": round(usd, 2) if usd is not None else None,
            })
    except Exception as e:  # noqa: BLE001
        out["tokens_error"] = str(e)[:120]

    priced = [t for t in tokens if t["usd"]]
    priced.sort(key=lambda t: t["usd"], reverse=True)
    total = sum(t["usd"] for t in priced) + (out.get("native", {}).get("usd") or 0)
    out["token_count"] = len(tokens)
    out["tokens"] = priced[:limit] if priced else tokens[:limit]
    out["total_usd"] = round(total, 2)
    out["source"] = "Blockscout v2 (free, public)"
    return out


# ------------------------------- pendle --------------------------------------
def pendle_markets(chain: str = "eth", limit: int = 15) -> Dict[str, Any]:
    cid = CHAIN_IDS.get(chain.lower(), 1)
    data = _get(f"{PENDLE_BASE}/v1/{cid}/markets/active")
    mk = data.get("markets", data if isinstance(data, list) else [])
    rows = []
    for m in mk:
        det = m.get("details") or {}
        rows.append({
            "name": m.get("name"), "address": m.get("address"),
            "expiry": (m.get("expiry") or "")[:10],
            "implied_apy_pct": round(_num(det.get("impliedApy")) * 100, 2),
            "pendle_apy_pct": round(_num(det.get("pendleApy")) * 100, 2),
            "aggregated_apy_pct": round(_num(det.get("aggregatedApy")) * 100, 2),
            "liquidity_usd": round(_num(det.get("liquidity"))),
            "is_new": bool(m.get("isNew")), "is_prime": bool(m.get("isPrime")),
        })
    rows.sort(key=lambda r: r["liquidity_usd"], reverse=True)
    return {"chain": chain.lower(), "chain_id": cid, "market_count": len(rows),
            "markets": rows[:limit], "source": "Pendle API v2 (free, public)"}


def pendle_wallet(address: str, chain: str = "eth", limit: int = 20) -> Dict[str, Any]:
    cid = CHAIN_IDS.get(chain.lower(), 1)
    q = urllib.parse.urlencode({"user": address, "limit": min(limit, 100),
                                "skip": 0, "chainId": cid})
    try:
        data = _get(f"{PENDLE_BASE}/v4/{cid}/transactions?{q}")
    except Exception:
        data = _get(f"{PENDLE_BASE}/v4/{cid}/transactions?" +
                    urllib.parse.urlencode({"user": address, "limit": min(limit, 100)}))
    txs = data.get("results", data.get("transactions", data if isinstance(data, list) else []))
    rows = []
    for t in txs[:limit]:
        rows.append({
            "action": t.get("action") or t.get("type"),
            "market": (t.get("market") or {}).get("name") if isinstance(t.get("market"), dict) else t.get("market"),
            "valuation_usd": round(_num((t.get("valuation") or {}).get("usd"))) if isinstance(t.get("valuation"), dict) else None,
            "implied_apy_pct": round(_num(t.get("impliedApy")) * 100, 3) if t.get("impliedApy") is not None else None,
            "timestamp": t.get("timestamp"),
        })
    return {"address": address, "chain": chain.lower(), "tx_count": len(rows),
            "transactions": rows, "source": "Pendle API v2 (free, public)"}


# ------------------------------- yields --------------------------------------
def defi_yields(chain: Optional[str] = None, project: Optional[str] = None,
                symbol: Optional[str] = None, min_tvl: float = 1_000_000,
                stable_only: bool = False, limit: int = 20) -> Dict[str, Any]:
    data = _get(LLAMA_POOLS, timeout=30)
    pools = data.get("data", [])
    ch = LLAMA_CHAIN.get(chain.lower(), chain).lower() if chain else None
    pj = project.lower() if project else None
    sy = symbol.upper() if symbol else None
    res = []
    for p in pools:
        if _num(p.get("tvlUsd")) < min_tvl:
            continue
        if ch and (p.get("chain") or "").lower() != ch:
            continue
        if pj and pj not in (p.get("project") or "").lower():
            continue
        if sy and sy not in (p.get("symbol") or "").upper():
            continue
        if stable_only and not p.get("stablecoin"):
            continue
        res.append({
            "chain": p.get("chain"), "project": p.get("project"), "symbol": p.get("symbol"),
            "apy_pct": round(_num(p.get("apy")), 2),
            "apy_base_pct": round(_num(p.get("apyBase")), 2),
            "apy_reward_pct": round(_num(p.get("apyReward")), 2),
            "tvl_usd": round(_num(p.get("tvlUsd"))),
            "stablecoin": bool(p.get("stablecoin")), "il_risk": p.get("ilRisk"),
            "pool_id": p.get("pool"),
        })
    res.sort(key=lambda r: r["apy_pct"], reverse=True)
    return {"filters": {"chain": chain, "project": project, "symbol": symbol,
                        "min_tvl": min_tvl, "stable_only": stable_only},
            "pool_count": len(res), "pools": res[:limit],
            "source": "DeFiLlama Yields (free, public)",
            "disclaimer": "APY is variable and historical; DYOR, not financial advice."}
