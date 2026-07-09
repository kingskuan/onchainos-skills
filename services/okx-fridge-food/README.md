# Fridge-to-Recipe ASP

**"What can I cook right now?"** — Tell the agent what's in your fridge, get 3 recipes you can make immediately, with step-by-step instructions, cooking time, calories, and a shopping list for missing items.

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
curl -X POST http://localhost:8000/cook \
  -H 'Content-Type: application/json' \
  -d '{
    "ingredients": ["egg", "tomato", "rice", "garlic", "pasta"],
    "servings": 2,
    "max_time_minutes": 30,
    "difficulty": "easy",
    "cuisine": "any"
  }'
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | Health check |
| POST | /cook | Get recipes (debug) |
| GET | /a2a/manifest | A2A service manifest |
| POST | /a2a/invoke | A2A invocation |

## Input Options

| Field | Type | Default | Description |
|---|---|---|---|
| ingredients | array | required | What's in your fridge |
| servings | int | 2 | How many people |
| max_time_minutes | int | 30 | Max cooking time |
| difficulty | string | easy | easy / medium / hard |
| cuisine | string | any | chinese, japanese, italian, etc. |
| dietary | array | [] | vegetarian, vegan, gluten-free, dairy-free |
| exclude | array | [] | Ingredients to avoid |

## Output

- **recipes**: Top 3 matching recipes with steps, tips, times, calories
- **shopping_list**: Unified list of missing ingredients across all recipes
- **markdown**: Full formatted report ready to display

## Deployment (Railway)

1. Push to GitHub
2. Railway → New Project → Deploy from GitHub
3. No environment variables required — zero config

## No API Keys Required

All recipe matching is done using a built-in curated recipe database — instant response, no external dependencies.

## Cuisine Support

Chinese 🇨🇳 · Japanese 🇯🇵 · Italian 🇮🇹 · Mexican 🇲🇽 · Thai 🇹🇭 · Indian 🇮🇳 · American 🇺🇸 · Mediterranean 🌊 · Korean 🇰🇷
