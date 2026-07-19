# YtOS — On-chain DeFi Intelligence ASP

A paid Agent Service Provider (ASP) that wraps the **DeFi Dashboard** data layer
into one A2A/MCP endpoint. **$0.3 USDT per call** on X Layer (`eip155:196`) via
OKX x402. All data comes from **free public APIs** — no keys, no vendor lock-in.

## Tools

| `tool`           | What it does                                              | Source        |
|------------------|----------------------------------------------------------|---------------|
| `wallet`         | Wallet portfolio: native + ERC-20 balances, USD value    | Blockscout v2 |
| `pendle_markets` | Active Pendle YT/PT markets: implied APY, liquidity       | Pendle API v2 |
| `pendle_wallet`  | A wallet's Pendle activity (swaps, valuations)            | Pendle API v2 |
| `yields`         | Cross-chain yield pools, filtered + ranked by APY         | DeFiLlama     |

Chains: `eth`, `base`, `optimism`, `arbitrum`, `polygon`, `gnosis`, `bsc`.

## API

- `GET  /health` — liveness (free)
- `GET  /a2a/manifest` — service manifest (free)
- `POST /a2a/invoke` — main entrypoint (**paid**)
- `POST /query` — same as invoke, typed response (**paid**)
- `POST /mcp` — MCP-style `{tool, arguments}` dispatch (**paid**)

### Examples

```bash
# Wallet portfolio
curl -sX POST $URL/a2a/invoke \
  -H 'content-type: application/json' \
  -d '{"tool":"wallet","address":"0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"}'

# Best cross-chain stablecoin yields over $5M TVL
curl -sX POST $URL/a2a/invoke \
  -d '{"tool":"yields","stable_only":true,"min_tvl":5000000,"limit":10}'

# Pendle markets on Base
curl -sX POST $URL/a2a/invoke -d '{"tool":"pendle_markets","chain":"base"}'
```

Requests are camelCase/synonym tolerant (`minTvl`, `stableOnly`, `assistant`
for `tool`, `wallet` for `address`) so a paid call never 422s on a field-name
mismatch.

## Payment

The x402 gate (`app/okx_payment.py`, official `okxweb3-app-x402[evm]` SDK) is
**off** until credentials are set, so it never fails closed. Enable with:

```
OKX_API_KEY / OKX_SECRET_KEY / OKX_PASSPHRASE   # facilitator creds
PAY_TO=0x…                                       # seller address (X Layer)
PAY_NETWORK=eip155:196                           # X Layer (default)
PAY_SYNC_SETTLE=1                                # wait for on-chain confirm
```

`$0.3` → `300000` base units of USDT (6 decimals) at
`0x779ded0c9e1022225f8e0630b35a9b54be713736`.

## Develop

```bash
pip install -r requirements.txt
pytest -q                                   # 11 offline tests (network stubbed)
uvicorn app.main:app --reload --port 8080
```

## Deploy

Dockerfile + `railway.toml` included. Health check `/health`, `PORT=8080`.
Data disclaimer: APY is variable and historical — DYOR, not financial advice.
