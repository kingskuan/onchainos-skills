from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

# TheMealDB — 100% free, no API key
_BASE = "https://www.themealdb.com/api/json/v1/1"
_TIMEOUT = int(os.getenv("FETCH_TIMEOUT", "10"))

# Simple in-memory cache
_cache: Dict[str, Tuple[float, Any]] = {}
_TTL = 300  # 5 min


def _get(path: str, params: Optional[Dict[str, str]] = None) -> Any:
    key = path + str(params)
    now = time.time()
    if key in _cache and now - _cache[key][0] < _TTL:
        return _cache[key][1]
    url = _BASE + path
    try:
        resp = httpx.get(url, params=params, timeout=_TIMEOUT)
        data = resp.json()
        _cache[key] = (now, data)
        return data
    except Exception:
        return {}


def search_by_ingredient(ingredient: str) -> List[Dict[str, str]]:
    """Return list of {idMeal, strMeal, strMealThumb} for the ingredient."""
    data = _get("/filter.php", {"i": ingredient.lower().strip()})
    return data.get("meals") or []


def get_meal_detail(meal_id: str) -> Optional[Dict[str, Any]]:
    """Return full meal detail including all 20 ingredient/measure slots."""
    data = _get("/lookup.php", {"i": meal_id})
    meals = data.get("meals")
    if not meals:
        return None
    return meals[0]


def get_meal_ingredients(meal: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Extract (ingredient, measure) pairs, filtering empty slots."""
    pairs = []
    for i in range(1, 21):
        ing = (meal.get(f"strIngredient{i}") or "").strip()
        mea = (meal.get(f"strMeasure{i}") or "").strip()
        if ing:
            pairs.append((ing.lower(), mea))
    return pairs


def _infer_difficulty(meal: Dict[str, Any], n_ingredients: int) -> str:
    inst = (meal.get("strInstructions") or "").lower()
    steps = inst.count("\n") + inst.count("step") + inst.count(".")
    if n_ingredients <= 5 and steps <= 8:
        return "Easy"
    elif n_ingredients <= 10 and steps <= 15:
        return "Medium"
    return "Hard"


def _infer_time(meal: Dict[str, Any], n_ingredients: int) -> int:
    base = max(10, n_ingredients * 4)
    inst = meal.get("strInstructions", "")
    if "bake" in inst.lower() or "oven" in inst.lower():
        base += 30
    if "simmer" in inst.lower() or "slow" in inst.lower():
        base += 20
    return min(base, 90)


def find_recipes(
    fridge: List[str],
    dietary: List[str],
    max_missing: int = 3,
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """
    1. Search each fridge ingredient → collect candidate meal IDs
    2. Fetch details for top candidates
    3. Score by match fraction
    4. Return top_n sorted by score
    """
    fridge_set: Set[str] = {i.lower().strip() for i in fridge}

    # Gather candidates via ingredient search
    meal_hit_count: Dict[str, int] = {}
    meal_stub: Dict[str, Dict] = {}

    for ing in fridge:
        results = search_by_ingredient(ing)
        for r in results:
            mid = r["idMeal"]
            meal_hit_count[mid] = meal_hit_count.get(mid, 0) + 1
            meal_stub[mid] = r

    # Sort by how many fridge ingredients matched
    sorted_ids = sorted(meal_hit_count, key=lambda x: meal_hit_count[x], reverse=True)

    # Fetch details for top candidates (up to 15 to pick best 3)
    candidates = []
    seen = set()
    for mid in sorted_ids[:15]:
        if mid in seen:
            continue
        seen.add(mid)
        detail = get_meal_detail(mid)
        if not detail:
            continue

        # Dietary filter (basic)
        name_lower = (detail.get("strMeal") or "").lower()
        category   = (detail.get("strCategory") or "").lower()
        tags_lower = (detail.get("strTags") or "").lower()

        if "vegetarian" in dietary and any(
            m in name_lower + category + tags_lower
            for m in ["beef", "chicken", "pork", "fish", "seafood", "lamb", "meat"]
        ):
            continue
        if "dairy-free" in dietary and any(
            m in name_lower + category + tags_lower
            for m in ["cheese", "cream", "butter", "milk"]
        ):
            pass  # approximate check — skip for MVP

        ing_pairs = get_meal_ingredients(detail)
        all_ings  = {p[0] for p in ing_pairs}
        have      = sorted(fridge_set & all_ings)
        missing   = sorted(all_ings - fridge_set)

        if len(missing) > max_missing:
            continue
        if not have:
            continue

        score = len(have) / max(len(all_ings), 1)

        candidates.append({
            "detail":   detail,
            "ing_pairs": ing_pairs,
            "have":     have,
            "missing":  missing,
            "score":    score,
        })

    # Sort by score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_n]
