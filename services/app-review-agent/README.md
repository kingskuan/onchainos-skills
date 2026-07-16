# App Review Analysis Agent

Read-only analysis of **public** App Store & Google Play reviews: rating trends,
sentiment, the themes users love vs complain about, extracted bugs and feature
requests, and competitor comparison. Built to run as a paid **A2MCP service
endpoint** for an OKX.AI ASP, usable as a plain REST/MCP API today.

> **Read-only and legitimate.** This service only *reads and analyzes* public
> reviews (Apple's official RSS `customerreviews` feed + Google Play public
> data). It does **not** post, generate, or manipulate reviews or ratings.

## What it does

`/analyze?platform=ios&app_id=310633997`:

- **Rating distribution** (1–5★) + official overall rating vs the recent sample
- **Sentiment split** — positive / neutral / negative share of recent reviews
- **Loved themes** vs **complaint themes** — keyword/bigram extraction split by
  positive vs negative reviews (what users praise vs what frustrates them)
- **Top issues** — reviews mentioning crashes/bugs/lag/errors, worst-rated first
- **Feature requests** — reviews asking for new capabilities
- **Rating trend** — recent-half vs older-half average (improving/declining)
- **Sample reviews** — representative positive & negative quotes

> Note: the review feed is sorted **most-recent**, so the sampled average skews
> toward recent sentiment and is typically lower than the lifetime rating. That
> recency bias is the point — it surfaces what's going wrong (or right) *now*.
> Both `overall_rating` (official lifetime) and `sample_avg_rating` are returned.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service info + MCP tool manifest |
| GET | `/health` | Liveness |
| GET | `/app/search?platform=ios&term=notion` | Find an app id / package |
| GET | `/reviews?platform=ios&app_id=310633997&pages=3` | Raw recent reviews |
| GET | `/analyze?platform=ios&app_id=310633997&pages=5` | Full analysis (core) |
| GET | `/compare?platform=ios&app_ids=310633997,1386412985` | Compare apps |
| POST | `/mcp` | MCP dispatch: `{"tool":"analyze_app_reviews","arguments":{"platform":"ios","app_id":"310633997"}}` |

- `platform` = `ios` or `android`
- `app_id` = Apple numeric id (e.g. `310633997`) or Android package (e.g. `com.whatsapp`)
- `country` = ISO country (default `us`); `pages` = review pages (≈50/page, max 10)

## Data sources

- **App Store**: Apple iTunes Search/Lookup API + the official App Store RSS
  `customerreviews` feed — free, no key.
- **Google Play**: the public `google-play-scraper` library (no official API).

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
curl "http://127.0.0.1:8000/analyze?platform=ios&app_id=310633997"
```

## Deploy to Railway

1. Push to GitHub.
2. Railway → New Project → Deploy from GitHub repo.
3. Set **Root Directory** to `services/app-review-agent`.
4. Railway detects the `Dockerfile` and injects `$PORT`. Deploy → public URL is
   your ASP service endpoint (e.g. `https://<app>.up.railway.app/mcp`).

## Payments (x402) — optional, off by default

Same x402 gate as the other agents. Enable with env vars:

| Var | Meaning | Example |
|---|---|---|
| `PAY_ENABLED` | Turn the 402 gate on | `1` |
| `PAY_PRICE` | Per-call price | `0.03` |
| `PAY_ASSET` / `PAY_ASSET_ADDRESS` | Token symbol / contract | `USDT` / `0x...` |
| `PAY_DECIMALS` / `PAY_NETWORK` | Decimals / network | `6` / `xlayer` |
| `PAY_ADDRESS` | ASP receiving address (`payTo`) | `0x...` |
| `FACILITATOR_URL` | x402 facilitator (verify/settle) | `https://...` |

Fails closed when enabled without a facilitator (never serves unverified).

## Disclaimer

Analysis of public review data for product/research insight. Not affiliated with
Apple or Google. Read-only — no reviews are posted or altered.
