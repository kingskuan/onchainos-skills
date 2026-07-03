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
| POST | `/mcp` | MCP-style dispatch: `{"tool":"research_stock","arguments":{"ticker":"AAPL"}}` |

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

To gate the API behind per-call payment (for the OKX A2MCP/x402 buyer flow),
set env vars:

| Var | Meaning | Example |
|---|---|---|
| `PAY_ENABLED` | Turn the 402 gate on | `1` |
| `PAY_PRICE` | Per-call price | `0.05` |
| `PAY_ASSET` | Asset | `USDT` |
| `PAY_ADDRESS` | ASP receiving address | `0x...` |

When enabled, calls without an `X-PAYMENT` header get an HTTP 402 with an
`accepts` payment-requirements body. This is a stub aligned with the x402
`exact` scheme — wire it to the OKX settlement/verify flow before going live.

## Limits / roadmap

- **US-listed filers only** (EDGAR). Non-US tickers are on the roadmap.
- **Per-product / per-geography segments** are not in EDGAR companyfacts
  (they live in dimensional XBRL) — planned via the frames + R-file parser.
- Yahoo analyst data is best-effort (crumb-gated) and degrades cleanly.

## Disclaimer

Informational only, not investment advice. Data from public filings and Yahoo
Finance; verify before acting.
