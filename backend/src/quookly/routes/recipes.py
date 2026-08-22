"""Recipe endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from quookly.contracts.discovery import SuggestionView
from quookly.contracts.errors import (
    AddressNotAllowed,
    ContentRefused,
    ContentUnreachable,
    ContentUnreadable,
    InferenceNotConfigured,
    InferenceRefused,
    InferenceUnavailable,
    IngredientNotRegistered,
    NotARecipe,
    StructuredOutputUnusable,
    UnknownUnit,
    UnsuitableForTheTable,
    UnsupportedDocument,
    YieldUnknown,
)
from quookly.contracts.exchange import ExchangeDocument
from quookly.contracts.measure import DecimalString
from quookly.contracts.recipe import (
    GenerationInput,
    ImportedRecipe,
    PresentedRecipe,
    RecipeInput,
    RecipeSummaryView,
    UrlImport,
)
from quookly.managers import recipe as recipe_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()

#: The language a document is exported in. Deliberately fixed rather than the cook's own:
#: the format carries one locale's names, and English is the language every registry is
#: defined in — so an English export is the one that resolves on any instance. Exporting a
#: cook's own language would make a document readable on fewer instances rather than more.
EXPORT_LOCALE = "en-GB"


@router.get("/recipes/suggestions", response_model=list[SuggestionView])
async def suggest_recipes(
    cook: CurrentCook,
    q: Annotated[str | None, Query(max_length=200, description="Words to search for.")] = None,
) -> list[SuggestionView]:
    """What to cook, best first, and why (UC-3.1, UC-3.3, UC-3.4).

    With words, a search: only what matched, in the order it matched, with the kitchen
    breaking ties. Without them, a suggestion: everything the cook has, ordered by what it
    would save — food about to go off first, then what needs no shopping trip.

    Each answer carries its reasons. A list that only reordered itself would be asking to
    be trusted rather than earning it.
    """
    return await recipe_manager.suggest(cook.cook_id, q)


@router.get("/recipes", response_model=list[RecipeSummaryView])
async def list_recipes(cook: CurrentCook) -> list[RecipeSummaryView]:
    """The cook's own recipes."""
    return await recipe_manager.list_for(cook.cook_id)


@router.post("/recipes", response_model=PresentedRecipe, status_code=status.HTTP_201_CREATED)
async def create_recipe(submitted: RecipeInput, cook: CurrentCook) -> PresentedRecipe:
    """Author a recipe."""
    try:
        return await recipe_manager.author(submitted, cook.cook_id)
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


class ImportOutcome(BaseModel):
    """What an import did."""

    recipes_added: int
    ingredients_added: int


# Declared before `/recipes/{recipe_id}`: they share a prefix, and the first match wins.
@router.post(
    "/recipes/generated", response_model=PresentedRecipe, status_code=status.HTTP_201_CREATED
)
async def generate_recipe(submitted: GenerationInput, cook: CurrentCook) -> PresentedRecipe:
    """Write a recipe that did not exist (UC-1.4, UC-1.5).

    A description, some ingredients to use up, or both. The household's constraints go into
    the asking, and the answer is judged independently against its resolved ingredients
    before anything is stored — a model asserting "this is dairy-free" carries no weight
    (ADR-006).

    A recipe the table cannot eat is refused **with its verdict**, because "no" without a
    reason is not an answer. That is stricter than importing on purpose: an imported recipe
    exists in the world whatever it contains, and this one was asked for on these people's
    behalf.
    """
    try:
        return await recipe_manager.generate(submitted, cook.cook_id)
    except UnsuitableForTheTable as refused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "What came back is not suitable for your household, so it has "
                "not been kept. Try again, or say more about what you want.",
                "verdict": jsonable_encoder(refused.verdict),
            },
        ) from None
    except NotARecipe:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Nothing usable came back. Try saying more about what you want.",
        ) from None
    except YieldUnknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="What came back does not say how much it makes, so it cannot be scaled.",
        ) from None
    except InferenceNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Writing a recipe needs a model, and this instance has none configured.",
        ) from None
    except InferenceRefused:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model provider refused the request. Check the instance's key.",
        ) from None
    except (InferenceUnavailable, StructuredOutputUnusable):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model could not be reached, or did not answer usefully. Please try again.",
        ) from None


@router.get("/recipes/export", response_model=ExchangeDocument)
async def export_recipes(cook: CurrentCook) -> ExchangeDocument:
    """Everything this cook owns, in the portable format (FR-11)."""
    return await recipe_manager.export_for(cook.cook_id, EXPORT_LOCALE)


@router.post("/recipes/import", response_model=ImportOutcome, status_code=status.HTTP_201_CREATED)
async def import_recipes(document: dict[str, Any], cook: CurrentCook) -> ImportOutcome:
    """Read an exported document into this instance (UC-1.2)."""
    try:
        result = await recipe_manager.import_document(document, cook.cook_id)
    except UnsupportedDocument as unreadable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"This file is not a Quookly export this version can read: {unreadable}",
        ) from None
    return ImportOutcome(
        recipes_added=result.recipes_added, ingredients_added=result.ingredients_added
    )


@router.get("/recipes/{recipe_id}", response_model=PresentedRecipe)
async def get_recipe(
    recipe_id: int,
    cook: CurrentCook,
    servings: DecimalString | None = Query(
        default=None,
        gt=0,
        description="Show the recipe at this yield, in whatever the recipe itself yields.",
    ),
) -> PresentedRecipe:
    """A recipe, scaled and in the cook's preferred units."""
    presented = await recipe_manager.present(recipe_id, cook.cook_id, servings=servings)
    if presented is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such recipe.")
    return presented


@router.post(
    "/recipes/import-url", response_model=ImportedRecipe, status_code=status.HTTP_201_CREATED
)
async def import_recipe_from_url(submitted: UrlImport, cook: CurrentCook) -> ImportedRecipe:
    """Read a recipe off a web page (UC-1.3).

    Every failure here is reported with what a cook can do about it. "It did not work" is
    a bug report; "this site will not serve an automated reader, but the page works in
    your browser" is an interface.
    """
    try:
        return await recipe_manager.import_from_url(submitted.url, cook.cook_id)
    except AddressNotAllowed as refused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(refused)
        ) from None
    except ContentRefused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That site will not serve an automated reader. The page works in your "
            "browser, so the recipe can be copied across by hand.",
        ) from None
    except ContentUnreachable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That page could not be fetched. Check the address and try again.",
        ) from None
    except ContentUnreadable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="There is nothing readable at that address.",
        ) from None
    except NotARecipe:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No recipe was found on that page.",
        ) from None
    except YieldUnknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That page does not say how much the recipe makes, so it cannot be "
            "scaled. Add it by hand to record the yield yourself.",
        ) from None
    except InferenceNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That page publishes no recipe data, so reading it needs a model — and "
            "this instance has none configured.",
        ) from None
    except InferenceRefused:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model provider refused the request. Check the instance's key.",
        ) from None
    except (InferenceUnavailable, StructuredOutputUnusable):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model could not be reached, or did not answer usefully. Please try again.",
        ) from None
