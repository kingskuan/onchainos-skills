from __future__ import annotations
from typing import Any, Dict
from .models import YtOSRequest
from .service import YtOSService


def get_manifest() -> Dict[str, Any]:
    return {
        "service_name": "ytos-defi-intel",
        "display_name": "YtOS",
        "version": "1.0.0",
        "pricing": {"amount": "0.3", "currency": "USDT", "per": "call", "network": "eip155:196"},
        "description": (
            "On-chain DeFi intelligence in one call: wallet portfolio valuation, "
            "Pendle yield-token markets and wallet activity, and cross-chain yield "
            "discovery — all from free public data sources, no API keys."
        ),
        "mode": "a2a",
        "capabilities": [
            "wallet_portfolio", "pendle_markets", "pendle_wallet", "defi_yields",
        ],
        "input_schema": {
            "type": "object",
            "required": ["tool"],
            "properties": {
                "tool": {"type": "string",
                         "enum": ["wallet", "pendle_markets", "pendle_wallet", "yields"],
                         "description": "Which data tool to run"},
                "address": {"type": "string",
                            "description": "Wallet address (wallet / pendle_wallet)",
                            "examples": ["0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"]},
                "chain": {"type": "string", "default": "eth",
                          "enum": ["eth", "base", "optimism", "arbitrum", "polygon", "gnosis", "bsc"]},
                "project": {"type": "string",
                            "description": "Protocol filter for yields e.g. aave-v3"},
                "symbol": {"type": "string",
                           "description": "Token/pool symbol filter for yields e.g. USDC"},
                "min_tvl": {"type": "number", "default": 1000000},
                "stable_only": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["tool", "data", "markdown"],
            "properties": {
                "tool":     {"type": "string"},
                "data":     {"type": "object"},
                "markdown": {"type": "string"},
                "meta":     {"type": "object"},
            },
        },
        "transport": {
            "protocol": "http",
            "methods": {
                "health":   {"method": "GET",  "path": "/health"},
                "manifest": {"method": "GET",  "path": "/a2a/manifest"},
                "invoke":   {"method": "POST", "path": "/a2a/invoke"},
            },
        },
        "notes": [
            "wallet: Blockscout v2 balances + USD valuation across 7 chains.",
            "pendle_markets / pendle_wallet: Pendle API v2 (YT/PT implied APY, liquidity).",
            "yields: DeFiLlama pools filtered by chain/project/symbol/TVL, ranked by APY.",
            "All data from free public APIs — no keys, no rate-limited vendor.",
        ],
    }


class A2AAdapter:
    def __init__(self, service: YtOSService) -> None:
        self.service = service

    def manifest(self) -> Dict[str, Any]:
        return get_manifest()

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = YtOSRequest.model_validate(payload)
        return self.service.run(req).model_dump()
