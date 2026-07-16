# Crypto Intel

On-demand crypto intel as a paid A2MCP ASP — **token safety heuristics** and
**cross-venue price spreads** from public DexScreener data (free, no key).

> Reimplements the *ideas* behind the Hermes
> [skill-packs](https://github.com/shunfeng8421/skill-packs) (defi-security-scanner
> + crypto-arb) from public data — not the original packs' code. Read-only,
> heuristic, **not financial advice**.

## What it does

- **`/token/{address}`** — token safety scan: liquidity depth, buy/sell honeypot
  signal, pair age, FDV-vs-liquidity, volatility → a 0–100 score, a verdict
  (`high risk` / `caution` / `lower risk`), and explicit flags. `?chain=` optional.
- **`/spread?q=<symbol|address>`** — cross-venue price spread for **one** token
  (resolves a symbol to its top-liquidity token address first, so it compares the
  same token across DEXes — not unrelated copycats).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | info + MCP manifest |
| GET | `/health` | liveness |
| GET | `/token/{address}?chain=ethereum` | token safety scan |
| GET | `/spread?q=PEPE` | cross-venue spread |
| POST | `/mcp` | `{"tool":"token_safety","arguments":{"address":"0x…"}}` |

## Pricing

Flat **$1 / call** on the paid routes, via the OKX x402 gate
(`app/okx_payment.py`; off until `OKX_API_KEY/SECRET/PASSPHRASE` + `PAY_TO` set).

## Data source

[DexScreener](https://dexscreener.com) public API — free, no key. 6+ chains.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
curl "http://127.0.0.1:8000/token/0x6982508145454ce325ddbe47a25d4ec3d2311933?chain=ethereum"
```

## Deploy to Railway

Push → New Project → Deploy from GitHub → **Root Directory** `services/crypto-intel`.
`$PORT` injected. Set payment env vars to enable the $1 gate.

## Disclaimer

Heuristic signals from public DEX data — not a safety guarantee, not investment
advice. Spreads may not be capturable after fees/gas/slippage/bridge. DYOR.
