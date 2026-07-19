from __future__ import annotations

from typing import Any, Dict, List

from . import clients
from .models import YtOSRequest, YtOSResponse


def _fmt_usd(v: Any) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _md_wallet(d: Dict[str, Any]) -> str:
    lines = [f"### Wallet portfolio — `{d.get('address')}` on {d.get('chain')}",
             f"**Total value:** {_fmt_usd(d.get('total_usd'))}  ·  "
             f"**Tokens:** {d.get('token_count', 0)}"]
    nat = d.get("native") or {}
    if nat.get("amount") is not None:
        lines.append(f"- **{nat.get('symbol','ETH')}** (native): "
                     f"{nat.get('amount')}  ·  {_fmt_usd(nat.get('usd'))}")
    toks = d.get("tokens") or []
    if toks:
        lines.append("")
        lines.append("| Token | Amount | Value |")
        lines.append("|---|---|---|")
        for t in toks:
            lines.append(f"| {t.get('symbol') or '?'} | {t.get('amount')} | "
                         f"{_fmt_usd(t.get('usd'))} |")
    lines.append(f"\n_Source: {d.get('source')}_")
    return "\n".join(lines)


def _md_pendle_markets(d: Dict[str, Any]) -> str:
    lines = [f"### Pendle active markets — {d.get('chain')} "
             f"({d.get('market_count', 0)} total)",
             "| Market | Expiry | Implied APY | Pendle APY | Liquidity |",
             "|---|---|---|---|---|"]
    for m in d.get("markets", []):
        lines.append(f"| {m.get('name')} | {m.get('expiry')} | "
                     f"{m.get('implied_apy_pct')}% | {m.get('pendle_apy_pct')}% | "
                     f"{_fmt_usd(m.get('liquidity_usd'))} |")
    lines.append(f"\n_Source: {d.get('source')}_")
    return "\n".join(lines)


def _md_pendle_wallet(d: Dict[str, Any]) -> str:
    lines = [f"### Pendle activity — `{d.get('address')}` on {d.get('chain')} "
             f"({d.get('tx_count', 0)} tx)",
             "| Action | Market | Value | Implied APY |",
             "|---|---|---|---|"]
    for t in d.get("transactions", []):
        apy = t.get("implied_apy_pct")
        apy_cell = f"{apy}%" if apy is not None else "—"
        lines.append(f"| {t.get('action')} | {t.get('market')} | "
                     f"{_fmt_usd(t.get('valuation_usd'))} | {apy_cell} |")
    lines.append(f"\n_Source: {d.get('source')}_")
    return "\n".join(lines)


def _md_yields(d: Dict[str, Any]) -> str:
    f = d.get("filters", {})
    lines = [f"### DeFi yields ({d.get('pool_count', 0)} pools match)",
             f"_Filters: chain={f.get('chain') or 'any'}, "
             f"project={f.get('project') or 'any'}, symbol={f.get('symbol') or 'any'}, "
             f"min_tvl={_fmt_usd(f.get('min_tvl'))}, stable_only={f.get('stable_only')}_",
             "",
             "| Chain | Project | Symbol | APY | TVL | Stable |",
             "|---|---|---|---|---|---|"]
    for p in d.get("pools", []):
        lines.append(f"| {p.get('chain')} | {p.get('project')} | {p.get('symbol')} | "
                     f"{p.get('apy_pct')}% | {_fmt_usd(p.get('tvl_usd'))} | "
                     f"{'✓' if p.get('stablecoin') else ''} |")
    lines.append(f"\n_Source: {d.get('source')}_  ·  {d.get('disclaimer','')}")
    return "\n".join(lines)


class YtOSService:
    """DeFi data ASP: wallet portfolio, Pendle markets/activity, and yield
    discovery — all via free public APIs (Blockscout / Pendle / DeFiLlama)."""

    def run(self, req: YtOSRequest) -> YtOSResponse:
        if req.tool == "wallet":
            if not req.address:
                raise ValueError("`address` is required for the wallet tool")
            data = clients.wallet_portfolio(req.address, req.chain, req.limit)
            md = _md_wallet(data)
        elif req.tool == "pendle_markets":
            data = clients.pendle_markets(req.chain, req.limit)
            md = _md_pendle_markets(data)
        elif req.tool == "pendle_wallet":
            if not req.address:
                raise ValueError("`address` is required for the pendle_wallet tool")
            data = clients.pendle_wallet(req.address, req.chain, req.limit)
            md = _md_pendle_wallet(data)
        elif req.tool == "yields":
            # "eth" is the model default; treat it as "no chain filter" so a bare
            # yields call returns the best cross-chain pools. Any explicit chain
            # (base, arbitrum, …) narrows it.
            yc = None if (req.chain or "eth").lower() == "eth" else req.chain
            data = clients.defi_yields(
                chain=yc, project=req.project, symbol=req.symbol,
                min_tvl=req.min_tvl, stable_only=req.stable_only, limit=req.limit)
            md = _md_yields(data)
        else:  # pragma: no cover — Literal guards this
            raise ValueError(f"unknown tool: {req.tool}")

        return YtOSResponse(
            tool=req.tool, data=data, markdown=md,
            meta={"chain": req.chain, "source": data.get("source")})
