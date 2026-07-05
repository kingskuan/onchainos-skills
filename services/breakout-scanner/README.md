# Breakout Scanner

On-demand version of the **BreakoutAnalysis** idea, as an A2MCP ASP service:
scan the whole US market for volume-driven breakouts, gate them on long-term
quality, and get an AI plain-English read (with news) per mover — plus a market
briefing. No "staring at the screen all day."

> Inspired by [BreakoutAnalysis](https://github.com/calesthio/BreakoutAnalysis).
> That project is a scheduled bot (pushes to Discord/email every 15 min); this
> exposes the same core as **request/response** endpoints a buyer agent can call
> and pay for. Informational only, not investment advice.

## What it does

- **`/scan`** — screens the **entire US market** via the TradingView scanner for
  breakouts: big % move + unusual volume, with a two-tier bar (large caps qualify
  at +6%, smaller names need +10%). All thresholds are query params.
- **Quality gate** (`?quality=true`) — keeps only names with real long-term
  strength (positive ~1y return or trading in the upper half of the 52-week
  range), using free Yahoo history (in place of Alpaca).
- **`/analyze/{ticker}`** — AI plain-English "why it's moving," tied to recent
  news headlines, with levels to watch and the key risk.
- **`/briefing`** — S&P 500 / NASDAQ / Dow / VIX levels + an AI market summary.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | info + MCP manifest |
| GET | `/health` | liveness |
| GET | `/scan?min_change_percent=6&min_relative_volume=2&quality=true&limit=30` | market breakout scan |
| GET | `/analyze/{ticker}` | AI breakout analysis + news + quality |
| GET | `/briefing` | market briefing |
| POST | `/mcp` | dispatch: `{"tool":"scan_breakouts","arguments":{"quality":true}}` |

Scan filters (query params, all optional): `min_change_percent`, `min_volume`,
`min_relative_volume`, `min_price`, `max_price`, `min_market_cap`, `quality`,
`limit`.

## Data sources (free, no key)

- **TradingView** public scanner (`scanner.tradingview.com/america/scan`) — whole-market screen
- **Yahoo Finance** — 1y history (quality gate), index levels, news headlines
- **LLM** (OpenAI-compatible, default DeepSeek) for the AI analysis/briefing

Alpaca (from the original) is replaced by Yahoo history so no brokerage key is
needed. To use Alpaca's SIP feed for higher accuracy, that's a future add.

## Run locally

```bash
pip install -r requirements.txt
export LLM_API_KEY=...   # OpenAI-compatible; default DeepSeek
uvicorn app.main:app --reload --port 8000
curl "http://127.0.0.1:8000/scan?quality=true&limit=10"
```

## Deploy to Railway

Push, then New Project → Deploy from GitHub → **Root Directory**
`services/breakout-scanner`. Set `LLM_API_KEY`. `$PORT` is injected.

## Payments (x402)

Same OKX x402 gate as the other ASP services (`app/okx_payment.py`), off until
`OKX_API_KEY/SECRET/PASSPHRASE` + `PAY_TO` are set. Suggested: scan $0.10,
analyze/briefing $0.05. See `docs/payment-integration-onboarding.md`.

## Disclaimer

Informational/research only, not investment advice. Not affiliated with
TradingView, Yahoo, or Alpaca.
