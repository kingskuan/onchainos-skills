"""Offline tests — clients are monkeypatched so no network is hit."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import clients
from app.main import app
from app.models import YtOSRequest
from app.service import YtOSService

client = TestClient(app)


# --------------------------- fixtures / stubs --------------------------------
@pytest.fixture(autouse=True)
def stub_clients(monkeypatch):
    monkeypatch.setattr(clients, "wallet_portfolio", lambda a, c="eth", limit=25: {
        "address": a, "chain": c, "native": {"symbol": "ETH", "amount": 1.5, "usd": 4500.0},
        "token_count": 2,
        "tokens": [{"symbol": "USDC", "name": "USD Coin", "amount": 1000.0, "usd": 1000.0},
                   {"symbol": "WBTC", "name": "Wrapped BTC", "amount": 0.1, "usd": 6000.0}],
        "total_usd": 11500.0, "source": "Blockscout v2 (free, public)"})
    monkeypatch.setattr(clients, "pendle_markets", lambda c="eth", limit=15: {
        "chain": c, "chain_id": 1, "market_count": 1,
        "markets": [{"name": "PT-sUSDe", "address": "0xabc", "expiry": "2025-12-25",
                     "implied_apy_pct": 12.5, "pendle_apy_pct": 3.2,
                     "aggregated_apy_pct": 15.7, "liquidity_usd": 50000000,
                     "is_new": False, "is_prime": True}],
        "source": "Pendle API v2 (free, public)"})
    monkeypatch.setattr(clients, "pendle_wallet", lambda a, c="eth", limit=20: {
        "address": a, "chain": c, "tx_count": 1,
        "transactions": [{"action": "swap", "market": "PT-sUSDe",
                          "valuation_usd": 1200, "implied_apy_pct": 11.1,
                          "timestamp": "2025-07-01T00:00:00Z"}],
        "source": "Pendle API v2 (free, public)"})
    monkeypatch.setattr(clients, "defi_yields", lambda **kw: {
        "filters": kw, "pool_count": 1,
        "pools": [{"chain": "Ethereum", "project": "aave-v3", "symbol": "USDC",
                   "apy_pct": 5.4, "apy_base_pct": 5.4, "apy_reward_pct": 0.0,
                   "tvl_usd": 900000000, "stablecoin": True, "il_risk": "no",
                   "pool_id": "abc"}],
        "source": "DeFiLlama Yields (free, public)",
        "disclaimer": "APY is variable and historical; DYOR, not financial advice."})


# ------------------------------- service -------------------------------------
def test_wallet_tool():
    svc = YtOSService()
    r = svc.run(YtOSRequest(tool="wallet", address="0xd8dA"))
    assert r.tool == "wallet"
    assert r.data["total_usd"] == 11500.0
    assert "Total value" in r.markdown and "$11,500.00" in r.markdown


def test_wallet_requires_address():
    svc = YtOSService()
    with pytest.raises(ValueError):
        svc.run(YtOSRequest(tool="wallet"))


def test_pendle_markets_tool():
    r = YtOSService().run(YtOSRequest(tool="pendle_markets", chain="eth"))
    assert r.data["market_count"] == 1
    assert "PT-sUSDe" in r.markdown


def test_pendle_wallet_tool():
    r = YtOSService().run(YtOSRequest(tool="pendle_wallet", address="0xd8dA"))
    assert r.data["tx_count"] == 1
    assert "swap" in r.markdown


def test_yields_tool():
    r = YtOSService().run(YtOSRequest(tool="yields", symbol="USDC", stable_only=True))
    assert r.data["pool_count"] == 1
    assert "aave-v3" in r.markdown


def test_camelcase_aliases():
    # a paid caller passing camelCase / synonyms must not 422
    req = YtOSRequest.model_validate(
        {"assistant": "yields", "minTvl": 5000000, "stableOnly": True, "top": 5})
    assert req.tool == "yields" and req.min_tvl == 5000000
    assert req.stable_only is True and req.limit == 5


# ------------------------------- http ----------------------------------------
def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_manifest_pricing():
    m = client.get("/a2a/manifest").json()
    assert m["display_name"] == "YtOS"
    assert m["pricing"]["amount"] == "0.3"
    assert m["pricing"]["network"] == "eip155:196"


def test_invoke():
    r = client.post("/a2a/invoke", json={"tool": "pendle_markets", "chain": "eth"})
    assert r.status_code == 200
    assert r.json()["data"]["market_count"] == 1


def test_mcp_dispatch():
    r = client.post("/mcp", json={"tool": "yields", "arguments": {"symbol": "USDC"}})
    assert r.status_code == 200
    assert r.json()["data"]["pool_count"] == 1


def test_query_endpoint():
    r = client.post("/query", json={"tool": "wallet", "address": "0xd8dA"})
    assert r.status_code == 200
    assert r.json()["tool"] == "wallet"
