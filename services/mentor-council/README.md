# Mentor Council

Decision advice through **methodology frameworks** — inspired by public thinkers'
documented work, **branded by method, never impersonating anyone**. Ask one
framework, or convene a **council** that routes your question to the most
relevant frameworks, lets them debate, and synthesizes a verdict (and shows
where they disagree — the shareable part).

Built to run as paid A2MCP ASP endpoints for OKX.AI; usable as a REST/MCP API.

> **Not impersonation.** Each framework applies a *method* (first-principles,
> inversion, antifragility, …) inspired by a public thinker. It never claims to
> be that person, and every answer carries a transparency note. Brands are the
> method/domain, not the person — respecting naming rules and publicity rights.

## Why a council (the viral mechanic)

14 separate "ask-a-guru" bots aren't interesting. One question analyzed by a
*panel that disagrees* — Musk-style "just build it" vs Munger-style "invert,
what kills this" — is novel and screenshot-worthy. The council is the flagship;
individual frameworks are building blocks.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Info + framework catalog + MCP manifest |
| GET | `/health` | Liveness |
| GET | `/mentors` | List methodology frameworks |
| POST | `/mentor/{key}` | One framework's take — `{"question": "..."}` |
| POST | `/council` | **Roundtable/debate** — `{"question": "...", "k": 3}` |
| POST | `/mcp` | MCP dispatch: `{"tool":"council","arguments":{"question":"..."}}` |

## Frameworks (methodology-branded)

`first-principles` · `inversion` · `antifragile` · `viral-content` ·
`startup-instinct` · `product-design` · `wealth-leverage` · `ai-engineering` ·
`learning` · `product-org` — each inspired by a public thinker's documented
approach; see `app/personas.py`.

## Run locally

```bash
pip install -r requirements.txt
export LLM_API_KEY=...   # OpenAI-compatible (default DeepSeek, cheap)
uvicorn app.main:app --reload --port 8000
curl -X POST localhost:8000/council -H 'content-type: application/json' \
  -d '{"question":"Should I quit my job to build a content brand?"}'
```

## LLM config (pluggable, default DeepSeek)

| Var | Default |
|---|---|
| `LLM_API_KEY` | — (required) |
| `LLM_BASE_URL` | `https://api.deepseek.com` |
| `LLM_MODEL` | `deepseek-chat` |

No key → endpoints return `{"available": false}`.

## Deploy to Railway

Push, then New Project → Deploy from GitHub → **Root Directory**
`services/mentor-council`. Set `LLM_API_KEY` as a service variable. The
`Dockerfile` injects `$PORT`.

## Payments (x402)

Same pluggable x402 gate as the other agents (`app/payments.py`); off by
default. Suggested pricing: single mentor cheap (~$0.2), council premium
(~$1–2, covers ~5 LLM calls).

## Disclaimer

Research/《decision-support》 only, not professional or investment advice. Frameworks
are distilled from public information and are not the views of any real person.
