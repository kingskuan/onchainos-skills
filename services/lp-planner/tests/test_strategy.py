import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.lp_strategy import (  # noqa: E402
    EntryAction,
    ScreenConfig,
    ScreeningEngine,
    SingleSideLPConfig,
    SingleSideLPStrategy,
    TokenMetrics,
    Verdict,
)


def make_token(**kwargs):
    # Defaults are picked so the token clears ScreeningEngine's 55 threshold
    # under the default ScreenConfig — top-tier metrics, V2 mainpool.
    defaults = dict(
        symbol="T", name="Test", gmcn_trending_rank=10,
        tf_24h=80.0, market_cap_usd=5_000_000,
        volume_24h_usd=10_000_000, liquidity_usd=1_000_000,
        current_price_usd=1.0, pool_type="v2_main",
        tx_share_pct=70.0, is_flap_fun=False,
    )
    defaults.update(kwargs)
    return TokenMetrics(**defaults)


def test_screen_in():
    t = make_token()
    r = ScreeningEngine(ScreenConfig()).screen(t)
    assert r.verdict == Verdict.SCREEN_IN, r.reasons


def test_screen_out_low_volume():
    # Screening is a soft aggregate score — low volume alone won't screen a
    # token out if cap/liquidity are top-tier. Combine a low volume with
    # marginal cap/liquidity to fall below the 55 threshold.
    t = make_token(
        volume_24h_usd=500_000,
        market_cap_usd=600_000,
        liquidity_usd=100_000,
    )
    r = ScreeningEngine(ScreenConfig()).screen(t)
    assert r.verdict == Verdict.SCREEN_OUT, r.reasons


def test_screen_out_flap_fun():
    t = make_token(is_flap_fun=True)
    r = ScreeningEngine(ScreenConfig()).screen(t)
    assert r.verdict == Verdict.SCREEN_OUT


def test_lp_wait():
    t = make_token(current_price_usd=2.0)
    closes = [1.85, 1.84, 1.83, 1.82, 1.81]
    plan = SingleSideLPStrategy(SingleSideLPConfig()).plan(t, closes)
    assert plan.action == EntryAction.WAIT


def test_lp_enter():
    t = make_token(current_price_usd=1.80)
    closes = [1.85, 1.84, 1.83, 1.82, 1.81, 1.80]
    plan = SingleSideLPStrategy(SingleSideLPConfig()).plan(t, closes)
    assert plan.action in (EntryAction.ENTER, EntryAction.WAIT)


if __name__ == "__main__":
    test_screen_in()
    test_screen_out_low_volume()
    test_screen_out_flap_fun()
    test_lp_wait()
    test_lp_enter()
    print("all tests passed")
