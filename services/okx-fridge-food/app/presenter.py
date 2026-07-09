from __future__ import annotations

from typing import List, Set

from .models import Recipe, RecipeRequest, RecipeResponse


DIFF_ICON = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
CUISINE_FLAG = {
    "chinese": "🇨🇳", "japanese": "🇯🇵", "italian": "🇮🇹",
    "mexican": "🇲🇽", "thai": "🇹🇭", "indian": "🇮🇳",
    "american": "🇺🇸", "mediterranean": "🌊", "korean": "🇰🇷",
    "any": "🌍",
}


def _recipe_block(r: Recipe, idx: int) -> str:
    flag = CUISINE_FLAG.get(r.cuisine, "")
    diff = DIFF_ICON.get(r.difficulty, "")
    lines = [
        f"## {idx}. {r.name} {flag}",
        f"{diff} {r.difficulty.title()} · ⏱ {r.time_minutes} min · 🔥 {r.calories_per_serving} kcal/serving · {r.completeness_pct}% match",
        "",
        "**Ingredients you have:**",
        ", ".join(r.ingredients_used) if r.ingredients_used else "_Everything you need is available_",
        "",
    ]

    if r.missing_ingredients:
        lines += [
            "**You'll also need:**",
            ", ".join(r.missing_ingredients),
            "",
        ]

    lines += ["**Steps:**"]
    for s in r.steps:
        time_note = f" _{s.time_minutes} min_" if s.time_minutes else ""
        lines.append(f"{s.step}. {s.instruction}{time_note}")

    if r.tips:
        lines += ["", "**Tips:**"]
        for t in r.tips:
            lines.append(f"- 💡 {t}")

    return "\n".join(lines)


def render(req: RecipeRequest, recipes: List[Recipe]) -> RecipeResponse:
    # Build unified shopping list
    missing_all: List[str] = []
    for r in recipes:
        for m in r.missing_ingredients:
            if m not in missing_all:
                missing_all.append(m)

    # Markdown
    header = (
        f"# 🍳 What Can I Cook?\n\n"
        f"**Your fridge:** {', '.join(req.ingredients)}\n\n"
        f"Found **{len(recipes)} recipe{'s' if len(recipes) != 1 else ''}** you can make right now:\n"
    )

    if not recipes:
        body = (
            "\n> No matching recipes found with the current ingredients and filters.\n\n"
            "Try relaxing the difficulty, time, or cuisine filter, or add more ingredients."
        )
    else:
        body = "\n\n".join(_recipe_block(r, i + 1) for i, r in enumerate(recipes))

    shopping = ""
    if missing_all:
        shopping = "\n\n---\n## 🛒 Quick Shopping List\n" + "\n".join(f"- [ ] {m}" for m in missing_all)

    markdown = header + "\n" + body + shopping

    return RecipeResponse(
        ingredients_provided=req.ingredients,
        recipes=recipes,
        shopping_list=missing_all,
        markdown=markdown,
        meta={
            "servings": req.servings,
            "max_time_minutes": req.max_time_minutes,
            "dietary": req.dietary,
            "cuisine": req.cuisine,
        },
    )
