from __future__ import annotations

from .matcher import find_recipes
from .models import RecipeRequest, RecipeResponse
from .presenter import render


class RecipeService:
    def run(self, req: RecipeRequest) -> RecipeResponse:
        recipes = find_recipes(req)
        return render(req, recipes)
