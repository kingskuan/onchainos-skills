# lp_strategy.py
# -*- coding: utf-8 -*-
"""
Single-side LP screening and entry strategy.
Reconstructed from transcript:
- GMCN trending screening (TF 24h, market cap >= 500K, volume > 1.5M)
- Single-side USDG LP on Uniswap V2/V3
- Wait for token dip into range, collect fees on rebound
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Optional, Sequence
import json
import math
import statistics


# -----------------------------
# Data models
# -----------------------------

class Verdict(str, Enum):
    SCREEN_IN = "screen_in"
    SCREEN_OUT = "screen_out"


class EntryAction(str, Enum):
    WAIT = "wait"
    ENTER = "enter"
    SKIP = "skip"


@dataclass
class TokenMetrics:
    symbol: str
    name: str
    gmcn_trending_rank: int          # lower is better; 1 = top
    tf_24h: float                    # 24h trade flow signal, normalized 0-100
    market_cap_usd: float
    volume_24h_usd: float
    liquidity_usd: float
    current_price_usd: float
    pool_type: str                   # "v2_main", "v3", "other"
    tx_share_pct: float = 0.0        # % of TX going to mainpool/V2
    is_flap_fun: bool = False


@dataclass
class ScreenConfig:
    min_market_cap_usd: float = 500_000
    min_volume_24h_usd: float = 1_500_000
    max_gmcn_rank: int = 50
    min_liquidity_usd: float = 100_000
    min_tf_24h: float = 0.0
    avoid_flap_fun: bool = True
    require_mainpool_preference: bool = True


@dataclass
class SingleSideLPConfig:
    capital_usdg: float = 1_000.0
    range_width_pct: float = 0.035      # 3.5% range
    lower_buffer_pct: float = 0.015     # below support by 1.5%
    enter_buffer_pct: float = 0.004     # enter when price within 0.4% above upper bound
    max_slippage_pct: float = 0.005
    preferred_pool_type: str = "v2_main"
    min_tx_share_pct: float = 60.0
    allow_v3_fallback: bool = True


@dataclass
class ScreenResult:
    token: TokenMetrics
    verdict: Verdict
    score: float
    reasons: List[str]


@dataclass
class LPPlan:
    token: TokenMetrics
    action: EntryAction
    pool_type: str
    side: str
    entry_price: float
    lower_bound: float
    upper_bound: float
    capital_usdg: float
    notes: List[str]


# -----------------------------
# Screening
# -----------------------------

class ScreeningEngine:
    def __init__(self, cfg: ScreenConfig):
        self.cfg = cfg

    def screen(self, token: TokenMetrics) -> ScreenResult:
        reasons: List[str] = []
        score = 0.0

        if self.cfg.avoid_flap_fun and token.is_flap_fun:
            return ScreenResult(
                token=token,
                verdict=Verdict.SCREEN_OUT,
                score=-100.0,
                reasons=["flap.fun token excluded"],
            )

        if token.gmcn_trending_rank <= self.cfg.max_gmcn_rank:
            score += self._rank_score(token.gmcn_trending_rank)
            reasons.append(f"GMCN rank OK: {token.gmcn_trending_rank}")
        else:
            reasons.append(f"GMCN rank too low: {token.gmcn_trending_rank} > {self.cfg.max_gmcn_rank}")

        if token.tf_24h >= self.cfg.min_tf_24h:
            score += self._norm(token.tf_24h, 0, 100) * 15
            reasons.append(f"TF 24h OK: {token.tf_24h}")
        else:
            reasons.append(f"TF 24h below threshold: {token.tf_24h}")

        if token.market_cap_usd >= self.cfg.min_market_cap_usd:
            score += self._norm(token.market_cap_usd, self.cfg.min_market_cap_usd, self.cfg.min_market_cap_usd * 20) * 25
            reasons.append(f"market cap OK: ${token.market_cap_usd:,.0f}")
        else:
            reasons.append(f"market cap too small: ${token.market_cap_usd:,.0f}")

        if token.volume_24h_usd >= self.cfg.min_volume_24h_usd:
            score += self._norm(token.volume_24h_usd, self.cfg.min_volume_24h_usd, self.cfg.min_volume_24h_usd * 10) * 25
            reasons.append(f"24h volume OK: ${token.volume_24h_usd:,.0f}")
        else:
            reasons.append(f"24h volume too low: ${token.volume_24h_usd:,.0f}")

        if token.liquidity_usd >= self.cfg.min_liquidity_usd:
            score += self._norm(token.liquidity_usd, self.cfg.min_liquidity_usd, self.cfg.min_liquidity_usd * 20) * 20
            reasons.append(f"liquidity OK: ${token.liquidity_usd:,.0f}")
        else:
            reasons.append(f"liquidity too low: ${token.liquidity_usd:,.0f}")

        if self.cfg.require_mainpool_preference:
            if token.pool_type == "v2_main":
                score += 10
                reasons.append("mainpool V2 preferred")
            elif token.pool_type == "v3" and token.tx_share_pct >= self.cfg.min_tx_share_pct:
                score += 5
                reasons.append(f"V3 fallback accepted, tx_share={token.tx_share_pct}%")
            else:
                reasons.append(f"pool type not preferred: {token.pool_type}")

        verdict = Verdict.SCREEN_IN if score >= 55 else Verdict.SCREEN_OUT
        return ScreenResult(token=token, verdict=verdict, score=round(score, 2), reasons=reasons)

    @staticmethod
    def _rank_score(rank: int) -> float:
        return max(0.0, 20.0 * (1.0 - (rank - 1) / 49.0))

    @staticmethod
    def _norm(x: float, lo: float, hi: float) -> float:
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (x - lo) / (hi - lo)))


# -----------------------------
# Price / range helpers
# -----------------------------

def support_price(closes: Sequence[float], lookback: int = 20) -> float:
    if not closes:
        raise ValueError("closes required")
    return min(list(closes[-lookback:]))


def build_entry_range(
    current_price: float,
    closes: Sequence[float],
    cfg: SingleSideLPConfig,
) -> tuple:
    sup = support_price(closes)
    lower = sup * (1.0 - cfg.lower_buffer_pct)
    upper = lower * (1.0 + cfg.range_width_pct)

    if upper >= current_price:
        gap = max(cfg.enter_buffer_pct, 0.005)
        upper = current_price * (1.0 - gap)
        lower = upper / (1.0 + cfg.range_width_pct)

    return round(lower, 8), round(upper, 8)


def price_in_range(px: float, lower: float, upper: float) -> bool:
    return lower <= px <= upper


# -----------------------------
# Single-side LP decision engine
# -----------------------------

class SingleSideLPStrategy:
    def __init__(self, cfg: SingleSideLPConfig):
        self.cfg = cfg

    def plan(self, token: TokenMetrics, closes: Sequence[float]) -> LPPlan:
        current = token.current_price_usd
        lower, upper = build_entry_range(current, closes, self.cfg)

        notes: List[str] = []
        if token.pool_type == self.cfg.preferred_pool_type:
            notes.append("prefer mainpool V2 for higher TX flow")
        elif token.pool_type == "v3":
            notes.append("V3 fallback only if mainpool edge is weak")
        else:
            notes.append("non-preferred pool; reduce size or skip")

        if token.is_flap_fun:
            return LPPlan(
                token=token,
                action=EntryAction.SKIP,
                pool_type=token.pool_type,
                side="single_side_usdg",
                entry_price=current,
                lower_bound=lower,
                upper_bound=upper,
                capital_usdg=0.0,
                notes=["flap.fun token skipped due to thin liquidity"],
            )

        if token.pool_type == "v2_main":
            if price_in_range(current, lower, upper):
                action = EntryAction.ENTER
                side = "single_side_usdg"
                notes.append("current price inside target range; enter now")
            elif current > upper:
                action = EntryAction.WAIT
                side = "single_side_usdg"
                notes.append("wait for dip into range; keep funds in USDG")
            else:
                action = EntryAction.SKIP
                side = "single_side_usdg"
                notes.append("price below planned range; don't chase")
        else:
            if token.tx_share_pct >= self.cfg.min_tx_share_pct and price_in_range(current, lower, upper):
                action = EntryAction.ENTER
                side = "single_side_usdg"
                notes.append("V3 fallback accepted; tx share sufficient")
            else:
                action = EntryAction.WAIT if current > upper else EntryAction.SKIP
                side = "single_side_usdg"
                notes.append("V3 fallback not strong enough")

        capital = self.cfg.capital_usdg if action == EntryAction.ENTER else 0.0
        if action == EntryAction.ENTER:
            notes.append(f"deploy {capital:.2f} USDG single-side")

        return LPPlan(
            token=token,
            action=action,
            pool_type=token.pool_type,
            side=side,
            entry_price=current,
            lower_bound=lower,
            upper_bound=upper,
            capital_usdg=capital,
            notes=notes,
        )


# -----------------------------
# Orchestration
# -----------------------------

def run_screening_and_lp(
    candidates: Sequence[TokenMetrics],
    closes_by_symbol: dict,
    screen_cfg: ScreenConfig,
    lp_cfg: SingleSideLPConfig,
) -> dict:
    screener = ScreeningEngine(screen_cfg)
    lp = SingleSideLPStrategy(lp_cfg)

    screened: List[ScreenResult] = []
    plans: List[LPPlan] = []

    for token in candidates:
        result = screener.screen(token)
        screened.append(result)

        if result.verdict == Verdict.SCREEN_IN:
            closes = closes_by_symbol.get(token.symbol, [])
            if not closes:
                plans.append(
                    LPPlan(
                        token=token,
                        action=EntryAction.WAIT,
                        pool_type=token.pool_type,
                        side="single_side_usdg",
                        entry_price=token.current_price_usd,
                        lower_bound=token.current_price_usd * 0.97,
                        upper_bound=token.current_price_usd * 0.99,
                        capital_usdg=0.0,
                        notes=["no price history; wait for candles before entry"],
                    )
                )
            else:
                plans.append(lp.plan(token, closes))

    screened.sort(key=lambda r: r.score, reverse=True)
    plans.sort(key=lambda p: (p.action == EntryAction.ENTER, p.token.volume_24h_usd), reverse=True)

    return {
        "screened": [asdict(x) for x in screened],
        "plans": [asdict(x) for x in plans],
    }
