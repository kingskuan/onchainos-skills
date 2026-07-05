"""Real OKX x402 one-time-payment integration (official `okxweb3-app-x402` SDK).

This replaces the earlier hand-rolled x402 gate with the OKX facilitator flow:
the middleware issues the 402 challenge, verifies the buyer's signed credential
via the OKX facilitator, settles on-chain (EIP-3009 / Permit2 on X Layer), and
only then runs the handler — returning the `PAYMENT-RESPONSE` receipt header.

Enable by setting these env vars on the service (all required to turn it on):

  OKX_API_KEY / OKX_SECRET_KEY / OKX_PASSPHRASE   facilitator API creds
      (create at the OKX dev portal — Agentic Wallet / Payments)
  PAY_TO            seller receiving address (X Layer, EIP-55 checksummed 0x…)
  PAY_NETWORK       CAIP-2 network, default eip155:196 (X Layer)
  OKX_BASE_URL      facilitator base, default https://web3.okx.com
  PAY_SYNC_SETTLE   "1" (sync, wait for confirmation) / "0" (async)

If any credential is missing the gate stays OFF (endpoints serve free) so the
service never fails closed by accident — flip it on once creds are set.
"""
from __future__ import annotations

import os
from typing import Any


def _creds() -> tuple[str | None, str | None, str | None]:
    return (
        os.getenv("OKX_API_KEY"),
        os.getenv("OKX_SECRET_KEY"),
        os.getenv("OKX_PASSPHRASE"),
    )


def configured() -> bool:
    ak, sk, pp = _creds()
    return bool(ak and sk and pp and os.getenv("PAY_TO"))


def route(price: str) -> dict[str, Any]:
    """Build a route's `accepts` config. `price` like "0.3" or "$0.3"."""
    p = price if str(price).startswith("$") else f"${price}"
    return {
        "accepts": [
            {
                "scheme": "exact",
                "payTo": os.getenv("PAY_TO"),
                "price": p,
                "network": os.getenv("PAY_NETWORK", "eip155:196"),  # X Layer
            }
        ]
    }


def _build_middleware(routes: dict[str, Any]):
    if not configured():
        return None
    # Imported lazily so the SDK is only needed when payments are enabled.
    from x402.http.middleware.fastapi import payment_middleware_from_config
    from x402.http.okx_auth import OKXAuthConfig
    from x402.http.okx_facilitator_client import (
        OKXFacilitatorClient,
        OKXFacilitatorConfig,
    )
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    ak, sk, pp = _creds()
    facilitator = OKXFacilitatorClient(
        OKXFacilitatorConfig(
            auth=OKXAuthConfig(api_key=ak, secret_key=sk, passphrase=pp),
            base_url=os.getenv("OKX_BASE_URL", "https://web3.okx.com"),
            sync_settle=os.getenv("PAY_SYNC_SETTLE", "1") == "1",
        )
    )
    # Register the server-side scheme handler for exact@<network> (EVM / X Layer).
    # Without this the middleware raises "No scheme for exact on eip155:196".
    network = os.getenv("PAY_NETWORK", "eip155:196")
    schemes = [{"network": network, "server": ExactEvmServerScheme()}]
    return payment_middleware_from_config(
        routes, facilitator_client=facilitator, schemes=schemes
    )


def install(app, routes: dict[str, Any]) -> bool:
    """Attach the x402 payment middleware to a FastAPI app. Returns True if the
    gate was installed (creds present), False if left open (unconfigured)."""
    mw = _build_middleware(routes)
    if mw is None:
        return False

    @app.middleware("http")
    async def _x402_payment(request, call_next):  # noqa: ANN001
        return await mw(request, call_next)

    return True
