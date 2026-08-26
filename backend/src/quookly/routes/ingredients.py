"""Ingredient registry endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from quookly.contracts.errors import IngredientNotRegistered
from quookly.contracts.ingredient import (
    IngredientView,
    Origin,
    RegistryEntryView,
    RegistryPageView,
)
from quookly.managers import ingredient as ingredient_manager
from quookly.routes.dependencies import CurrentAdmin, CurrentCook

router = APIRouter()


@router.get("/ingredients", response_model=list[IngredientView])
async def search_ingredients(
    cook: CurrentCook,
    search: str = Query(min_length=1, max_length=100, description="Part of an ingredient name."),
) -> list[IngredientView]:
    """Find registry entries to point a recipe line, or a dietary constraint, at."""
    return await ingredient_manager.search(search, cook.cook_id)


@router.get("/registry", response_model=RegistryPageView)
async def list_registry(
    cook: CurrentCook,
    search: str | None = Query(
        default=None, min_length=1, max_length=100, description="Part of an ingredient name."
    ),
    origin: Origin | None = Query(
        default=None, description="Narrow to seeded entries, or to what imports invented."
    ),
    approved: bool | None = Query(
        default=None, description="Narrow to what has been reviewed, or to what awaits it."
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> RegistryPageView:
    """Browse the ingredient registry — the largest list in the app.

    Separate from `search_ingredients`, which exists to point a recipe line at an entry
    and stops at a handful. This is for looking at the registry itself: complete, paged
    and counted, so the entries an import invented can be found and reviewed.
    """
    return await ingredient_manager.browse(
        cook.cook_id,
        term=search,
        origin=origin,
        approved=approved,
        offset=offset,
        limit=limit,
    )


@router.post("/registry/{slug}/approved", response_model=RegistryEntryView)
async def approve_ingredient(slug: str, admin: CurrentAdmin) -> RegistryEntryView:
    """Record that this entry has been reviewed.

    An administrator's job, not a cook's: reading the registry is reference material, but
    signing an entry off is a statement about the instance. Idempotent — the question is
    whether anybody has looked, not how many times.
    """
    try:
        return await ingredient_manager.approve(slug)
    except IngredientNotRegistered as absent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such ingredient."
        ) from absent
