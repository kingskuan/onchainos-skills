from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from .models import Recipe, RecipeRequest, RecipeStep
from .recipe_db import RECIPES


def _normalise(items: List[str]) -> Set[str]:
    """Lowercase + strip for matching."""
    out = set()
    for item in items:
        w = item.lower().strip()
        out.add(w)
        # Singular/plural simple normalization
        if w.endswith("s") and len(w) > 3:
            out.add(w[:-1])
        else:
            out.add(w + "s")
    return out


def _match_recipe(
    recipe: Dict[str, Any],
    have: Set[str],
    req: RecipeRequest,
) -> Tuple[bool, int, List[str]]:
    """
    Returns (matches, completeness_pct, missing_ingredients).
    """
    required = _normalise(recipe.get("required", []))
    optional = _normalise(recipe.get("optional", []))
    needs_any = _normalise(recipe.get("needs_any", []))
    always_missing = recipe.get("always_missing", [])

    # Check required ingredients
    have_required = all(
        any(r in h or h in r for h in have) for r in required
    ) if required else True

    # Check needs_any (at least one must be present)
    if needs_any:
        have_any = any(
            any(n in h or h in n for h in have) for n in needs_any
        )
        if not have_any:
            return False, 0, []

    if not have_required:
        return False, 0, []

    # Check dietary restrictions
    dietary = req.dietary
    recipe_ok = recipe.get("dietary_ok", [])
    if dietary:
        for d in dietary:
            if d.lower() not in [r.lower() for r in recipe_ok]:
                return False, 0, []

    # Check cuisine filter
    if req.cuisine != "any" and recipe["cuisine"] != req.cuisine:
        return False, 0, []

    # Check time
    if recipe["time_minutes"] > req.max_time_minutes:
        return False, 0, []

    # Check difficulty
    difficulty_rank = {"easy": 1, "medium": 2, "hard": 3}
    if difficulty_rank.get(recipe["difficulty"], 1) > difficulty_rank.get(req.difficulty, 3):
        return False, 0, []

    # Check excludes
    all_ingredients = required | optional
    if any(
        any(e.lower() in ing or ing in e.lower() for ing in all_ingredients)
        for e in req.exclude
    ):
        return False, 0, []

    # Calculate completeness
    used = [i for i in (recipe.get("required", []) + recipe.get("optional", []))
            if any(i.lower() in h or h in i.lower() for h in have)]
    all_needed = recipe.get("required", []) + [i for i in recipe.get("optional", []) if i not in recipe.get("always_missing", [])]
    completeness = int(len(used) / max(len(all_needed), 1) * 100)

    # Missing ingredients = optional items not present + always_missing
    missing_optional = [
        i for i in recipe.get("optional", [])
        if not any(i.lower() in h or h in i.lower() for h in have)
        and i not in always_missing
    ][:3]
    missing = list(always_missing) + missing_optional

    return True, completeness, missing


def find_recipes(req: RecipeRequest) -> List[Recipe]:
    have = _normalise(req.ingredients)
    matched: List[Tuple[Recipe, int]] = []

    for rdata in RECIPES:
        ok, pct, missing = _match_recipe(rdata, have, req)
        if not ok:
            continue

        ingredients_used = [
            i for i in (rdata.get("required", []) + rdata.get("optional", []))
            if any(i.lower() in h or h in i.lower() for h in have)
        ]

        steps = [
            RecipeStep(
                step=s["step"],
                instruction=s["instruction"],
                time_minutes=s.get("time_minutes"),
            )
            for s in rdata["steps"]
        ]

        recipe = Recipe(
            name=rdata["name"],
            cuisine=rdata["cuisine"],
            difficulty=rdata["difficulty"],
            time_minutes=rdata["time_minutes"],
            servings=req.servings,
            calories_per_serving=rdata["calories_per_serving"],
            ingredients_used=ingredients_used,
            missing_ingredients=missing,
            steps=steps,
            tips=rdata.get("tips", []),
            completeness_pct=pct,
        )
        matched.append((recipe, pct))

    # Sort by completeness descending, then by time ascending
    matched.sort(key=lambda x: (-x[1], x[0].time_minutes))
    return [r for r, _ in matched[:3]]   # top 3
