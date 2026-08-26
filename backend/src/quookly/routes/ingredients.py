"""Ingredient registry endpoints."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from quookly.contracts.errors import IngredientNotRegistered, NameAlreadyMeans
from quookly.contracts.ingredient import (
    UNSET,
    Allergen,
    IngredientKind,
    IngredientView,
    Origin,
    RegistryEntryDetailView,
    RegistryEntryView,
    RegistryPageView,
)
from quookly.managers import ingredient as ingredient_manager
from quookly.routes.dependencies import CurrentAdmin, CurrentCook

router = APIRouter()

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such ingredient.")


class Correction(BaseModel):
    """What to change about an entry. A field left out is left alone.

    `density` and `piece_grams` are `None`-able *and* omittable, and the two mean
    different things: `null` clears the figure, which is a real correction because a wrong
    density is worse than none, while leaving the field out keeps it. `model_fields_set`
    is what tells them apart — a plain `None` default could not.
    """

    kind: IngredientKind | None = None
    density: Decimal | None = Field(default=None, ge=0)
    piece_grams: Decimal | None = Field(default=None, ge=0)


class Classification(BaseModel):
    """What an ingredient contains, as somebody who looked would say it.

    An empty list is an answer, not an omission — which is exactly why this is its own
    request and not a field on `Correction` (ADR-006).
    """

    allergens: list[Allergen]


class Renaming(BaseModel):
    """What one language should call this entry from now on."""

    locale: str = Field(min_length=2, max_length=10)
    name: str = Field(min_length=1, max_length=200)


class Naming(BaseModel):
    """What an entry is called in one language, canonical spelling first."""

    locale: str = Field(min_length=2, max_length=10)
    spellings: list[str] = Field(min_length=1)


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


@router.get("/registry/{slug}", response_model=RegistryEntryDetailView)
async def get_ingredient(slug: str, cook: CurrentCook) -> RegistryEntryDetailView:
    """One entry with every name it answers to.

    Readable by any signed-in cook: the registry is reference material, and what an
    ingredient is called elsewhere is the sort of thing somebody looks up. Changing it is
    another matter — the endpoints below are an administrator's.
    """
    found = await ingredient_manager.detail(slug)
    if found is None:
        raise NOT_FOUND
    return found


@router.put("/registry/{slug}", response_model=RegistryEntryView)
async def amend_ingredient(
    slug: str, correction: Correction, admin: CurrentAdmin
) -> RegistryEntryView:
    """Correct the facts an import guessed at: kind, density, piece weight.

    An administrator's, because the registry is shared — a density corrected here changes
    what every cook on this instance is shown, and an allergen would change what they are
    warned about.
    """
    supplied = correction.model_fields_set
    try:
        return await ingredient_manager.amend(
            slug,
            kind=correction.kind,
            density=correction.density if "density" in supplied else UNSET,
            piece_grams=correction.piece_grams if "piece_grams" in supplied else UNSET,
        )
    except IngredientNotRegistered as absent:
        raise NOT_FOUND from absent


@router.put("/registry/{slug}/allergens", response_model=RegistryEntryView)
async def classify_ingredient(
    slug: str, classification: Classification, admin: CurrentAdmin
) -> RegistryEntryView:
    """Record what this ingredient contains.

    Deliberately not part of `amend_ingredient`. A single request carrying the whole entry
    would make "I forgot to include the allergens" indistinguishable from "this ingredient
    is unexamined", turning a known-milk entry into an unknown one — which is the failure
    ADR-006 exists to prevent.
    """
    classified = await ingredient_manager.classify(slug, classification.allergens)
    if classified is None:
        raise NOT_FOUND
    return classified


@router.post("/registry/{slug}/names", response_model=RegistryEntryDetailView)
async def name_ingredient(
    slug: str, naming: Naming, admin: CurrentAdmin
) -> RegistryEntryDetailView:
    """Teach the registry what this entry is called in another language.

    Additive. An entry an import created is named only in the language of the page it came
    from, and adding the German for it must not cost the English.
    """
    try:
        named = await ingredient_manager.name(slug, naming.locale, naming.spellings)
    except NameAlreadyMeans as taken:
        # 409 rather than 422: the request is well formed and the caller could not have
        # known. The other entry is named because that is the useful part — two entries
        # claiming one name in one language are often one ingredient to be merged.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{taken.spelling!r} is already what this language calls {taken.slug!r}.",
        ) from taken
    if named is None:
        raise NOT_FOUND
    return named


@router.put("/registry/{slug}/name", response_model=RegistryEntryDetailView)
async def rename_ingredient(
    slug: str, renaming: Renaming, admin: CurrentAdmin
) -> RegistryEntryDetailView:
    """Change what one language calls this entry.

    Separate from `name_ingredient`, which adds a spelling. This decides which of them is
    the name — the one a cook is shown and a shopping list is written with. The previous
    one is demoted rather than removed, so pages that use it still resolve.
    """
    try:
        renamed = await ingredient_manager.rename(slug, renaming.locale, renaming.name)
    except IngredientNotRegistered as absent:
        raise NOT_FOUND from absent
    except NameAlreadyMeans as taken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{taken.spelling!r} is already what this language calls {taken.slug!r}.",
        ) from taken
    if renamed is None:
        raise NOT_FOUND
    return renamed
