from __future__ import annotations
from typing import Any, Dict
from .models import RecipeRequest
from .service import RecipeService


def get_manifest() -> Dict[str, Any]:
    return {
        "service_name": "fridge-recipe-asp",
        "display_name": "FridgeFood",
        "version": "1.0.0",
        "pricing": {"amount": "1", "currency": "USDT", "per": "call", "network": "eip155:196"},
        "description": (
            "Tell me what's in your fridge and I'll give you 3 recipes you can cook right now — "
            "with step-by-step instructions, cooking time, calories, and a shopping list for anything missing."
        ),
        "mode": "a2a",
        "capabilities": [
            "ingredient_matching", "recipe_generation", "dietary_filtering",
            "shopping_list", "step_by_step_instructions",
        ],
        "input_schema": {
            "type": "object",
            "required": ["ingredients"],
            "properties": {
                "ingredients":        {"type": "array",   "items": {"type": "string"},
                                       "examples": [["egg", "tomato", "rice", "garlic"]]},
                "servings":           {"type": "integer",  "default": 2, "minimum": 1, "maximum": 10},
                "max_time_minutes":   {"type": "integer",  "default": 30},
                "difficulty":         {"type": "string",   "default": "easy", "enum": ["easy","medium","hard"]},
                "cuisine":            {"type": "string",   "default": "any",
                                       "enum": ["any","chinese","japanese","italian","mexican","thai","indian","american","mediterranean","korean"]},
                "dietary":            {"type": "array",    "items": {"type": "string"}, "default": [],
                                       "examples": [["vegetarian","gluten-free"]]},
                "exclude":            {"type": "array",    "items": {"type": "string"}, "default": []},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["recipes", "markdown"],
            "properties": {
                "ingredients_provided": {"type": "array"},
                "recipes":              {"type": "array"},
                "shopping_list":        {"type": "array"},
                "markdown":             {"type": "string"},
                "meta":                 {"type": "object"},
            },
        },
        "transport": {
            "protocol": "http",
            "methods": {
                "health":   {"method": "GET",  "path": "/health"},
                "manifest": {"method": "GET",  "path": "/a2a/manifest"},
                "invoke":   {"method": "POST", "path": "/a2a/invoke"},
            },
        },
        "notes": [
            "Recipe matching works without any external API — instant response.",
            "Use dietary filters (vegetarian, vegan, gluten-free, dairy-free) for personalization.",
            "Returns top 3 recipes ranked by ingredient match completeness.",
        ],
    }


class A2AAdapter:
    def __init__(self, service: RecipeService) -> None:
        self.service = service

    def manifest(self) -> Dict[str, Any]:
        return get_manifest()

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = RecipeRequest.model_validate(payload)
        return self.service.run(req).model_dump()
