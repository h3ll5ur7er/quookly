"""Recipe endpoints."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from quookly.contracts.errors import IngredientNotRegistered, UnknownUnit
from quookly.contracts.recipe import PresentedRecipe, RecipeInput, RecipeSummaryView
from quookly.managers import recipe as recipe_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()

DEFAULT_LOCALE = "en-GB"


@router.get("/recipes", response_model=list[RecipeSummaryView])
async def list_recipes(cook: CurrentCook) -> list[RecipeSummaryView]:
    """The cook's own recipes."""
    return await recipe_manager.list_for(cook.cook_id)


@router.post("/recipes", response_model=PresentedRecipe, status_code=status.HTTP_201_CREATED)
async def create_recipe(submitted: RecipeInput, cook: CurrentCook) -> PresentedRecipe:
    """Author a recipe."""
    try:
        return await recipe_manager.author(submitted, cook.cook_id, DEFAULT_LOCALE)
    except UnknownUnit as unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown unit: {unknown}.",
        ) from None
    except IngredientNotRegistered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A line refers to an ingredient that is not in the registry.",
        ) from None


@router.get("/recipes/{recipe_id}", response_model=PresentedRecipe)
async def get_recipe(
    recipe_id: int,
    cook: CurrentCook,
    servings: Decimal | None = Query(
        default=None,
        gt=0,
        description="Show the recipe at this yield, in whatever the recipe itself yields.",
    ),
) -> PresentedRecipe:
    """A recipe, scaled and in the cook's preferred units."""
    presented = await recipe_manager.present(recipe_id, cook.cook_id, DEFAULT_LOCALE, servings)
    if presented is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such recipe.")
    return presented
