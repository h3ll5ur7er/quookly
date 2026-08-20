"""Ingredient registry endpoints."""

from fastapi import APIRouter, Query

from quookly.access import ingredient as registry
from quookly.contracts.ingredient import IngredientView
from quookly.routes.dependencies import CurrentCook

router = APIRouter()

DEFAULT_LOCALE = "en-GB"


@router.get("/ingredients", response_model=list[IngredientView])
async def search_ingredients(
    cook: CurrentCook,
    search: str = Query(min_length=1, max_length=100, description="Part of an ingredient name."),
) -> list[IngredientView]:
    """Find registry entries to point a recipe line at."""
    found = await registry.search(search, DEFAULT_LOCALE)
    return [
        IngredientView(id=entry.id, slug=entry.slug, name=entry.name, kind=entry.kind)
        for entry in found
    ]
