"""Ingredient registry endpoints."""

from fastapi import APIRouter, Query

from quookly.contracts.ingredient import IngredientView
from quookly.managers import ingredient as ingredient_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()


@router.get("/ingredients", response_model=list[IngredientView])
async def search_ingredients(
    cook: CurrentCook,
    search: str = Query(min_length=1, max_length=100, description="Part of an ingredient name."),
) -> list[IngredientView]:
    """Find registry entries to point a recipe line, or a dietary constraint, at."""
    return await ingredient_manager.search(search, cook.cook_id)
