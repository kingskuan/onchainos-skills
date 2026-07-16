# 数据洞察 · Data Insights ASP

An analyst-led **A2MCP ASP** for OKX.AI that turns tables and databases into
understandable insights and charts. **One ASP, four assistants** — flat **$1 / call**.

| Assistant | key | What it does |
|---|---|---|
| 数据分析师 Data Analyst | `data_analyst` | Statistical profile, correlations, IQR outliers, category distributions, narrative findings, and **Vega-Lite chart specs** a buyer agent can render. |
| 数据库分析师 Database Analyst | `database_analyst` | Loads your table into a sandboxed in-memory **SQLite**; runs a **read-only `SELECT`**, or translates a simple natural-language question to SQL. Writes are refused. |
| 表格操作员 Spreadsheet Operator | `spreadsheet_operator` | A pipeline of table ops: `filter / sort / select / derive / groupby+agg / limit`. |
| 快查助手 Quick Query | `quick_query` | One fast answer: `count / max / min / sum / mean / distinct / lookup` — or a live **OKX public spot price** ("price of BTC"). |

Deterministic — **no LLM key required**. It runs on the data you send.

## Input

Send a table as any of:
- `{"columns": ["a","b"], "rows": [[1,2],[3,4]]}`
- `[{"a":1,"b":2}, ...]` (list of records)
- `{"csv": "a,b\n1,2\n3,4"}`

```jsonc
// data_analyst
{"assistant": "data_analyst", "table": {...}}
// database_analyst
{"assistant": "database_analyst", "table": {...}, "sql": "SELECT region, SUM(sales) FROM data GROUP BY region"}
{"assistant": "database_analyst", "table": {...}, "question": "average sales by region"}
// spreadsheet_operator
{"assistant": "spreadsheet_operator", "table": {...},
 "ops": [{"op":"derive","column":"profit","expr":"sales - cost"},
         {"op":"filter","column":"profit","cmp":">","value":30},
         {"op":"sort","column":"profit","desc":true},{"op":"limit","n":5}]}
// quick_query
{"assistant": "quick_query", "table": {...}, "op": {"op":"max","column":"sales"}}
{"assistant": "quick_query", "question": "price of BTC"}
```
Both snake_case and camelCase field names are accepted; unknown keys are ignored,
so a minor field-name mismatch never fails a paid call.

## Endpoints

| Method | Path | |
|---|---|---|
| GET | `/health` | liveness (free) |
| GET | `/a2a/manifest` · `/service/manifest` | manifest (free) |
| POST | `/insights` | run an assistant ($1) |
| POST | `/a2a/invoke` | A2A invocation ($1) |
| POST | `/mcp` | `{"tool":"<assistant>","arguments":{...}}` ($1) |

## Payments (OKX Pay / x402)

Flat **$1 / call** on the paid routes via the shared OKX x402 gate
(`app/okx_payment.py`, network `eip155:196` / X Layer). Off until
`OKX_API_KEY/SECRET/PASSPHRASE` + `PAY_TO` are set. See
`docs/payment-integration-onboarding.md`.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
curl -s -X POST localhost:8000/insights -H 'Content-Type: application/json' \
  -d '{"assistant":"data_analyst","table":[{"region":"East","sales":120},{"region":"West","sales":200}]}'
```

## Deploy (Railway)

New Project → Deploy from repo → **Root Directory** `services/okx-data-insights`.
`Dockerfile` + `railway.toml` are detected; `$PORT` is injected. Set the payment
env vars to enable the $1 gate.

## Disclaimer

Analysis is computed deterministically from the data you provide; it is
informational and not financial advice.
