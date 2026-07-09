from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

DifficultyLevel = Literal["easy", "medium", "hard"]
CuisineType = Literal[
    "any", "chinese", "japanese", "italian", "mexican",
    "thai", "indian", "american", "mediterranean", "korean"
]


class RecipeRequest(BaseModel):
    # Accept snake_case + camelCase + synonyms so a paid call never 422s on a
    # minor field-name mismatch (which would waste an x402 settlement).
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    ingredients: List[str] = Field(
        ..., min_length=1, description="Ingredients currently in your fridge",
        validation_alias=AliasChoices("ingredients", "items", "fridge"))
    servings: int = Field(
        2, ge=1, le=10, description="Number of people to serve",
        validation_alias=AliasChoices("servings", "people", "diners"))
    max_time_minutes: int = Field(
        30, ge=5, le=180, description="Maximum cooking time in minutes",
        validation_alias=AliasChoices("max_time_minutes", "maxTimeMinutes", "max_time", "maxTime"))
    difficulty: DifficultyLevel = Field("easy", description="Preferred difficulty level")
    cuisine: CuisineType = Field("any", description="Preferred cuisine type")
    dietary: List[str] = Field(
        default_factory=list, description="Dietary restrictions e.g. vegetarian, gluten-free, dairy-free",
        validation_alias=AliasChoices("dietary", "diet", "restrictions"))
    exclude: List[str] = Field(
        default_factory=list, description="Ingredients to exclude",
        validation_alias=AliasChoices("exclude", "avoid"))


class RecipeStep(BaseModel):
    step: int
    instruction: str
    time_minutes: Optional[int] = None


class Recipe(BaseModel):
    name: str
    cuisine: str
    difficulty: DifficultyLevel
    time_minutes: int
    servings: int
    calories_per_serving: int
    ingredients_used: List[str]
    missing_ingredients: List[str]
    steps: List[RecipeStep]
    tips: List[str]
    completeness_pct: int      # how much of the recipe you can make right now


class RecipeResponse(BaseModel):
    ingredients_provided: List[str]
    recipes: List[Recipe]
    shopping_list: List[str]   # union of all missing ingredients, deduplicated
    markdown: str
    meta: Dict[str, Any] = Field(default_factory=dict)
