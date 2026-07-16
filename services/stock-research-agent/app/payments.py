"""x402 payment gate — standards-shaped, facilitator-pluggable.

Implements the seller/resource side of the x402 flow:

  1. no `X-PAYMENT`  → 402 + payment-requirements body (`accepts`)
  2. `X-PAYMENT`     → decode → facilitator `/verify` → `/settle` → 200
                       + `X-PAYMENT-RESPONSE` header (base64 settlement)

Verification/settlement is delegated to an x402 **facilitator** (set
`FACILITATOR_URL` — e.g. the OKX facilitator). Without one configured the gate
fails closed (returns 402) so paid content is never served unverified — unless
`X402_DEV_ACCEPT_UNVERIFIED=1` is set for local testing.

Config (env):
  PAY_ENABLED=1
  PAY_PRICE=0.05                 human amount
  PAY_ASSET=USDT                 token symbol (display)
  PAY_ASSET_ADDRESS=0x...        token contract (required for a real charge)
  PAY_DECIMALS=6
  PAY_NETWORK=xlayer
  PAY_ADDRESS=0x...              ASP receiving address (payTo)
  FACILITATOR_URL=https://...    x402 facilitator base URL
  X402_DEV_ACCEPT_UNVERIFIED=0   dev-only bypass (INSECURE)
"""
from __future__ import annotations

import base64
import json
import os
from decimal import Decimal
from typing import Any

import httpx

X402_VERSION = 1


def _env(k: str, default: str = "") -> str:
    return os.getenv(k, default)


def enabled() -> bool:
    return _env("PAY_ENABLED", "0") == "1"


def config() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "price": _env("PAY_PRICE", "0.05"),
        "asset": _env("PAY_ASSET", "USDT"),
        "asset_address": _env("PAY_ASSET_ADDRESS", ""),
        "decimals": int(_env("PAY_DECIMALS", "6")),
        "network": _env("PAY_NETWORK", "xlayer"),
        "pay_to": _env("PAY_ADDRESS", ""),
        "facilitator": _env("FACILITATOR_URL", ""),
        "dev_accept_unverified": _env("X402_DEV_ACCEPT_UNVERIFIED", "0") == "1",
        "scheme": "exact",
    }


def _atomic(price: str, decimals: int) -> str:
    try:
        return str(int(Decimal(price) * (Decimal(10) ** decimals)))
    except Exception:  # noqa: BLE001
        return "0"


def requirements(resource: str, description: str) -> dict[str, Any]:
    c = config()
    return {
        "x402Version": X402_VERSION,
        "accepts": [
            {
                "scheme": c["scheme"],
                "network": c["network"],
                "maxAmountRequired": _atomic(c["price"], c["decimals"]),
                "resource": resource,
                "description": description,
                "mimeType": "application/json",
                "payTo": c["pay_to"],
                "maxTimeoutSeconds": 60,
                "asset": c["asset_address"],
                "extra": {"name": c["asset"], "decimals": c["decimals"]},
            }
        ],
        "error": "X-PAYMENT header is required",
    }


def _decode_payment(header: str) -> dict[str, Any] | None:
    try:
        return json.loads(base64.b64decode(header).decode())
    except Exception:  # noqa: BLE001
        return None


async def verify_and_settle(
    client: httpx.AsyncClient, x_payment: str, resource: str, description: str
) -> tuple[bool, str, dict[str, Any] | None]:
    """Return (ok, reason, settlement). settlement → X-PAYMENT-RESPONSE."""
    c = config()
    payload = _decode_payment(x_payment)
    if payload is None:
        return False, "malformed X-PAYMENT header", None

    reqs = requirements(resource, description)["accepts"][0]

    if not c["facilitator"]:
        if c["dev_accept_unverified"]:
            return True, "dev-accept-unverified", {"mode": "dev", "verified": False}
        return False, "facilitator not configured (set FACILITATOR_URL)", None

    body = {
        "x402Version": X402_VERSION,
        "paymentPayload": payload,
        "paymentRequirements": reqs,
    }
    try:
        v = await client.post(
            f"{c['facilitator'].rstrip('/')}/verify", json=body, timeout=25
        )
        vj = v.json()
        if not vj.get("isValid"):
            return False, vj.get("invalidReason", "verification failed"), None
        s = await client.post(
            f"{c['facilitator'].rstrip('/')}/settle", json=body, timeout=30
        )
        sj = s.json()
        if not sj.get("success", sj.get("settled", False)):
            return False, sj.get("error", "settlement failed"), None
        return True, "settled", sj
    except Exception as e:  # noqa: BLE001
        return False, f"facilitator error: {str(e)[:120]}", None


def encode_response(settlement: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(settlement).encode()).decode()
