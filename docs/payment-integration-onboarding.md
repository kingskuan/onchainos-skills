# ASP Payment Integration — Onboarding Guide (x402 One-Time Payment)

> Goal: get a newly-registered ASP from "listed but earns nothing" to
> "collects a fee on every call" in ~10 minutes. This is the step most sellers
> miss — registering an ASP sets the *advertised* price, but the **endpoint
> itself must enforce payment** (or you serve for free).

**Official docs:** https://web3.okx.com/onchainos/dev-docs/payments/methods-onetime

---

## 0. The one thing to understand first

Two separate things carry a "price":

| Where | What it does | If you skip it |
|---|---|---|
| **ASP service metadata** (`agent create --service … "fee":"1"`) | *Advertises* the price in the marketplace | Buyers don't know the price |
| **Your endpoint's x402 gate** | *Collects* the money on each call | **You get paid $0** |

Registering the ASP is **not** enough. You must add the x402 middleware to the
endpoint. That's what this guide does.

---

## 1. How x402 one-time payment works (seller side)

```
Buyer → POST /your-endpoint                (no payment)
Seller ← 402 Payment Required              (WWW-Authenticate challenge: scheme/network/payTo/price)
Buyer → POST /your-endpoint                (Authorization / X-PAYMENT: signed EIP-3009 credential)
Seller → facilitator.verify()  → facilitator.settle()   (on-chain, X Layer)
Seller ← 200 OK + PAYMENT-RESPONSE header  (receipt / txHash) + your normal body
```

The **OKX facilitator** does the crypto: it verifies the buyer's signature
(+ KYT screening) and settles the transfer on-chain. Your server only wires up
the middleware and declares a price per route.

- **Network:** X Layer — CAIP-2 `eip155:196`
- **Tokens:** USD₮0, USDG by default (EIP-3009, gasless signing); any ERC-20 via
  Permit2 (`extra: { assetTransferMethod: "permit2" }`)
- **Settlement:** sync (wait for confirmation before `200`) or async

---

## 2. Install the SDK (Python / FastAPI)

```bash
# NOTE the [evm] extra — required for X Layer (eip155) settlement. Without it
# you get: RouteConfigurationError: No scheme for "exact" on "eip155:196".
pip install "okxweb3-app-x402[evm]" fastapi uvicorn
```

Other stacks (same semantics): Node `@okxweb3/x402-express` · Go
`github.com/okx/payments/go/x402` · Rust `okxweb3-app-x402-axum` · Java filter.

---

## 3. Get facilitator credentials

From the OKX dev portal (Agentic Wallet / Payments), create an API key — you get
three values used to authenticate to the facilitator:

- `OKX_API_KEY`
- `OKX_SECRET_KEY`
- `OKX_PASSPHRASE`

And decide your **receiving address** on X Layer (EIP-55 checksummed `0x…`):

- `PAY_TO`

> Treat these as secrets. Set them as platform/host env vars (e.g. Railway
> service variables) — **never commit them**.

---

## 4. Wire the middleware (FastAPI)

The minimal, correct integration (this is exactly what the reference services in
`services/*/app/okx_payment.py` do):

```python
import os
from fastapi import FastAPI
from x402.http.middleware.fastapi import payment_middleware_from_config
from x402.http.okx_auth import OKXAuthConfig
from x402.http.okx_facilitator_client import OKXFacilitatorClient, OKXFacilitatorConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme

app = FastAPI()

facilitator = OKXFacilitatorClient(OKXFacilitatorConfig(
    auth=OKXAuthConfig(
        api_key=os.environ["OKX_API_KEY"],
        secret_key=os.environ["OKX_SECRET_KEY"],
        passphrase=os.environ["OKX_PASSPHRASE"],
    ),
    base_url="https://web3.okx.com",
    sync_settle=True,          # wait for on-chain confirmation before 200
))

# route key = "METHOD /path" (supports a trailing /* wildcard)
routes = {
    "POST /mcp":        {"accepts": [{"scheme": "exact", "payTo": os.environ["PAY_TO"],
                                      "price": "$1.5", "network": "eip155:196"}]},
    "POST /m/*/mcp":    {"accepts": [{"scheme": "exact", "payTo": os.environ["PAY_TO"],
                                      "price": "$0.3", "network": "eip155:196"}]},
}

# REQUIRED: register the server-side scheme handler for exact@<network>.
# Omitting `schemes` → RouteConfigurationError "No scheme for exact on eip155:196".
schemes = [{"network": "eip155:196", "server": ExactEvmServerScheme()}]

mw = payment_middleware_from_config(routes, facilitator_client=facilitator, schemes=schemes)

@app.middleware("http")
async def x402(request, call_next):
    return await mw(request, call_next)
```

**Route config fields** (per `accepts` entry):

| Field | Meaning | Example |
|---|---|---|
| `scheme` | `exact` (fixed price), `charge` (splits), `upto` (cap) | `"exact"` |
| `network` | CAIP-2 chain | `"eip155:196"` (X Layer) |
| `payTo` | seller receiving address | `"0x…"` |
| `price` | dollar string | `"$0.3"` |
| `extra` | optional (e.g. Permit2) | `{"assetTransferMethod":"permit2"}` |

Unprotected routes (e.g. `GET /health`, `GET /`) are simply left out of `routes`.

---

## 5. Fail-open vs fail-closed (important)

Decide what happens when creds are **absent**:

- **Fail-open** (recommended during onboarding): if creds/`PAY_TO` are missing,
  don't attach the middleware — the service runs free. You flip payment on by
  setting env vars, no code change. (The reference `okx_payment.install()` does
  this.)
- **Fail-closed**: attach unconditionally — but note that without a reachable
  facilitator every protected call returns `402`/`502`, which will also block
  the marketplace reviewer. Don't enable payment enforcement until **after**
  your listing is approved and creds are set.

---

## 6. Test checklist

1. **Free path** (no creds): `GET /health` → `200`; a protected route → `200`
   (gate off).
2. **Enabled** (creds + `PAY_TO` set): protected route **without** payment →
   `402` with a `WWW-Authenticate`/`accepts` challenge.
3. **Paid**: a buyer agent (or the OKX buyer flow) calls with a signed
   `X-PAYMENT` → `200` + a `PAYMENT-RESPONSE` header carrying the settlement
   receipt/`txHash`.
4. Confirm the received amount lands at `PAY_TO` on X Layer.

---

## 7. Common pitfalls (seen in real onboarding)

- **"Registered but earning $0"** — the ASP fee is set but the endpoint has no
  x402 middleware. → This guide, §4.
- **Enabling payment before approval** — a fail-closed gate returns 402 to the
  reviewer and can block listing. → Keep it fail-open / off until approved (§5).
- **Wrong price format** — `price` must be a dollar string like `"$0.3"`, not a
  bare number or a token amount.
- **Wrong network** — X Layer is `eip155:196` (CAIP-2), not `196` or `xlayer`.
- **`No scheme for "exact" on "eip155:196"` (500)** — you installed the base SDK
  but not the EVM extra, or didn't pass `schemes=[…ExactEvmServerScheme()…]` to
  `payment_middleware_from_config`. Fix: `pip install "okxweb3-app-x402[evm]"`
  **and** register the scheme (§4). Validate creds up front with
  `OKXFacilitatorClient(...).get_supported()` — it lists the supported
  scheme/network kinds.
- **Secrets in the repo** — keep `OKX_*` and `PAY_TO` in host env vars only.
- **`$PORT` on PaaS** — bind uvicorn to `$PORT` via a shell (`sh -c 'uvicorn … --port ${PORT}'`),
  or the container 502s. (Unrelated to payments but bites every first deploy.)

---

## 8. Reference implementation

Working, env-driven integration used by the sample ASPs in this repo:

- `services/*/app/okx_payment.py` — the reusable wire-up (build + `install()`)
- `services/*/app/main.py` — `PAY_ROUTES = { … okx_payment.route("0.3") … }` +
  `okx_payment.install(app, PAY_ROUTES)`

Env vars to enable on the host:

```
OKX_API_KEY=…
OKX_SECRET_KEY=…
OKX_PASSPHRASE=…
PAY_TO=0x…              # X Layer receiving address
PAY_NETWORK=eip155:196  # optional (default)
PAY_SYNC_SETTLE=1       # optional (default sync)
```
