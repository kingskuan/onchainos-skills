# Stock Research Agent

A free-data stock-research API: deep single-stock analysis (StockAnalysis-style)
plus a lightweight screener (Finviz-lite). Built to run as a paid **A2MCP
service endpoint** for an OKX.AI ASP, but usable as a plain REST/MCP API today.

Data comes from **legitimate free sources** — [SEC EDGAR](https://www.sec.gov/edgar)
(official filings) and Yahoo Finance's public endpoints. It does **not** scrape
stockanalysis.com or finviz.com; it reproduces the same research value from
open data.

## What it does

For a single ticker (`/research/{ticker}`):

- **5-year financials** — revenue, gross/operating/net income, cash flow, capex,
  assets, equity — with year-over-year deltas
- **Growth** — 5-year revenue & earnings CAGR, growing/not flags
- **Valuation** — market cap, EV, P/E, P/S, P/B, EV/EBITDA
- **Financial health** — current ratio, debt/equity, net margin, Altman Z-score
  and a simple A–F grade (blow-up risk at a glance)
- **Analyst view** — mean/high/low target price, # of analysts, recommendation,
  and forward revenue/EPS estimates (best-effort via Yahoo)

Screening (`/screener`): filter a curated (or custom) universe by market cap,
P/E, P/S, net margin, and revenue growth.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service info + MCP tool manifest |
| GET | `/health` | Liveness |
| GET | `/research/{ticker}` | Deep single-stock research |
| GET | `/screener?min_market_cap=1e11&max_pe=30&min_revenue_cagr=0.08` | Screen |
| GET | `/analyze/{ticker}` | **AI analyst** — bull vs bear debate + rating, grounded on the data (needs LLM key) |
| POST | `/mcp` | MCP-style dispatch: `{"tool":"research_stock","arguments":{"ticker":"AAPL"}}` |

## AI analyst layer (the moat)

`/analyze/{ticker}` runs a lightweight multi-agent debate (bull vs bear → judge)
**grounded on this service's own structured data** — financials, valuation,
health score, and per-product/geography segments — and returns a rating
(`STRONG_BUY`…`STRONG_SELL`), confidence, thesis, key reasons, and risks. The
edge is the grounding: the model reasons over EDGAR-derived facts, not generic
web text. Inspired by the TradingAgents pattern, kept compact (2 debate calls +
1 judge) to stay fast and cheap.

Pluggable LLM (OpenAI-compatible) via env — default **DeepSeek** (cheap):

| Var | Meaning | Default |
|---|---|---|
| `LLM_API_KEY` | provider key (enables the layer) | — (required) |
| `LLM_BASE_URL` | OpenAI-compatible base URL | `https://api.deepseek.com` |
| `LLM_MODEL` | model id | `deepseek-chat` |

No key → `/analyze` degrades to `{"available": false}` and still returns the
grounding context; the free data endpoints are unaffected. Research support
only, not investment advice.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/research/AAPL
```

Or with Docker:

```bash
docker build -t stock-research-agent .
docker run -p 8000:8000 stock-research-agent
```

## Deploy to Railway

1. Push this repo to GitHub.
2. Railway → **New Project → Deploy from GitHub repo** → pick the repo.
3. If this lives in a monorepo subfolder, set **Root Directory** to
   `services/stock-research-agent`.
4. Railway detects the `Dockerfile` (or `Procfile`) and injects `$PORT`
   automatically — no extra config needed.
5. After deploy you get a public URL like `https://<app>.up.railway.app`.
   That URL (e.g. `https://<app>.up.railway.app/mcp`) is your ASP **service
   endpoint**.

## Payments (x402) — optional, off by default

Implements the seller side of the x402 flow: no `X-PAYMENT` → HTTP 402 with an
`accepts` payment-requirements body; with `X-PAYMENT` → decode → facilitator
`/verify` + `/settle` → 200 + `X-PAYMENT-RESPONSE` header. Verification is
delegated to a pluggable x402 **facilitator**.

| Var | Meaning | Example |
|---|---|---|
| `PAY_ENABLED` | Turn the 402 gate on | `1` |
| `PAY_PRICE` | Per-call price (human) | `0.05` |
| `PAY_ASSET` | Token symbol (display) | `USDT` |
| `PAY_ASSET_ADDRESS` | Token contract | `0x...` |
| `PAY_DECIMALS` | Token decimals | `6` |
| `PAY_NETWORK` | Settlement network | `xlayer` |
| `PAY_ADDRESS` | ASP receiving address (`payTo`) | `0x...` |
| `FACILITATOR_URL` | x402 facilitator base URL (verify/settle) | `https://...` |
| `X402_DEV_ACCEPT_UNVERIFIED` | Dev-only bypass — **insecure** | `0` |

**Fail-closed:** with `PAY_ENABLED=1` but no `FACILITATOR_URL`, paid paths
return 402 (never served unverified) unless `X402_DEV_ACCEPT_UNVERIFIED=1`.
Point `FACILITATOR_URL` at the OKX x402 facilitator to accept real payments.

## Limits / roadmap

- **US-listed filers only** (EDGAR). Non-US tickers are on the roadmap.
- **Per-product / per-geography segments** are not in EDGAR companyfacts
  (they live in dimensional XBRL) — planned via the frames + R-file parser.
- Yahoo analyst data is best-effort (crumb-gated) and degrades cleanly.

## Disclaimer

Informational only, not investment advice. Data from public filings and Yahoo
Finance; verify before acting.
