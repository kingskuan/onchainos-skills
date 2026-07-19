# LP Planner

Single-side USDG LP screening + entry planner, packaged as an A2MCP ASP
service. Given a set of candidate tokens and their recent close prices, this
service screens each token against GMCN-style filters (trending rank, TF-24h,
market cap, volume, liquidity, pool preference, flap.fun exclusion) and
produces a single-side LP entry plan (`WAIT` / `ENTER` / `SKIP`) around a
support band placed just below the recent low.

Ported from the original `lp_arb_railway_repo` prototype: same strategy math,
same JSON shape on `/run`, `/plans`, `/screened`. New in this version: FastAPI
+ MCP dispatch (`/mcp`), a `POST /run` that accepts custom candidates and
closes, a `POST /plan` for a single token, and the shared OKX x402 payment
gate used by the other services under `services/`.

## What it does

- **Token screening** — filters candidates by GMCN trending rank ≤ 50,
  TF-24h ≥ 0, market cap ≥ $500K, 24h volume ≥ $1.5M, liquidity ≥ $100K,
  prefers V2 mainpool (V3 fallback only if `tx_share_pct` ≥ 60%), excludes
  flap.fun tokens.
- **Single-side LP entry plan** — for each screened-in token:
  1. Find recent support from the closes (min of last 20).
  2. Place a range just below support: `lower = support × 0.985`,
     `upper = lower × 1.035` (3.5% wide).
  3. If current price is above the range → `WAIT` (funds stay in USDG).
  4. If current price is inside the range → `ENTER` (deploy single-side).
  5. If current price is below the range → `SKIP` (don't chase).

### 开仓计划说明

```
核心思路：
- 找到 token 的近期 support 区间
- 在 support 下方放置单边 USDG LP position
- 等待 token 下跌进入区间
- token 触底反弹时，position 吃手续费
- V2 mainpool 优先（0~∞ range，TX 流量最大）
- flap.fun 类 token 排除（流动性薄，执行风险高）

开仓条件：
  WAIT  → 当前价格在区间上方，等待回落
  ENTER → 当前价格进入区间，立即开仓
  SKIP  → 当前价格已跌破区间，不追
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/` | info + MCP manifest |
| GET  | `/health` | liveness |
| GET  | `/run` | run the built-in demo (4 sample tokens) |
| GET  | `/plans` | demo, plans array only |
| GET  | `/screened` | demo, screening array only |
| POST | `/run` | custom run: `{candidates, closes, screen_cfg?, lp_cfg?}` |
| POST | `/plan` | single-token plan: `{token, closes, lp_cfg?}` |
| POST | `/mcp` | dispatch: `{"tool":"screen_and_plan","arguments":{...}}` |

### `POST /run` body

```json
{
  "candidates": [
    {
      "symbol": "ABC",
      "name": "ABC Token",
      "gmcn_trending_rank": 12,
      "tf_24h": 78.0,
      "market_cap_usd": 1200000,
      "volume_24h_usd": 2400000,
      "liquidity_usd": 320000,
      "current_price_usd": 1.85,
      "pool_type": "v2_main",
      "tx_share_pct": 72.0,
      "is_flap_fun": false
    }
  ],
  "closes": { "ABC": [1.92, 1.90, 1.88, 1.86, 1.84, 1.83, 1.85] },
  "screen_cfg": { "min_market_cap_usd": 500000 },
  "lp_cfg":     { "capital_usdg": 1000.0 }
}
```

Response shape (same as `GET /run`):

```json
{
  "screened": [ { "token": {...}, "verdict": "screen_in", "score": 86.4, "reasons": [...] } ],
  "plans":    [ { "token": {...}, "action": "wait", "lower_bound": 1.803, "upper_bound": 1.866, ... } ]
}
```

## MCP tools

- `screen_and_plan` — args: `{candidates, closes, screen_cfg?, lp_cfg?}`
- `plan_token` — args: `{token, closes, lp_cfg?}` (skip the screen, plan one token)
- `demo_run` — no args, runs the built-in demo

## Run locally

```bash
cd services/lp-planner
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/run
```

Run the tests:

```bash
cd services/lp-planner
python -m pytest tests -q      # or: python tests/test_strategy.py
```

## Deploy to Railway

Push this repo, then in Railway: New Project → Deploy from GitHub →
**Root Directory** `services/lp-planner`. Railway picks up `railway.json` +
`Dockerfile` and injects `$PORT`. No env vars required for demo/paper mode.

## Payments (x402)

Same OKX x402 gate as the other ASP services (`app/okx_payment.py`), off until
`OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE` + `PAY_TO` are set.
Suggested prices: read endpoints `$0.05`, custom run `$0.10`, mcp `$0.10`.

## Wiring live data

Replace `DEMO_CANDIDATES` / `DEMO_CLOSES` in `app/main.py`, or (recommended)
call `POST /run` from your caller with candidates pulled from
GeckoTerminal / Dexscreener / GMCN. The screening + planner logic in
`app/lp_strategy.py` is pure — no I/O, easy to test.

## Disclaimer

Informational / research only, not investment advice.
