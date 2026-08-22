"""Access to recipes, in domain verbs.

A recipe is stored as three tables and returned as one whole thing, with its ingredient
lines resolved against the registry for the caller's locale. Callers deal in recipes;
rows and joins stay here.
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access import search
from quookly.access.database import session
from quookly.access.ingredient import allergens_within, canonical_names_within
from quookly.access.models import IngredientLineRow, IngredientRow, RecipeRow, StepRow
from quookly.contracts.errors import IngredientNotRegistered
from quookly.contracts.ingredient import Ingredient
from quookly.contracts.measure import Quantity
from quookly.contracts.recipe import (
    IngredientLine,
    Recipe,
    RecipeDraft,
    RecipeSummary,
    Step,
)
from quookly.contracts.suitability import JudgedLine


async def store(draft: RecipeDraft, cook_id: int) -> Recipe:
    """Persist a draft and return it whole."""
    row = RecipeRow(
        cook_id=cook_id,
        title=draft.title,
        summary=draft.summary,
        yield_magnitude=draft.yield_quantity.magnitude,
        yield_unit=draft.yield_quantity.unit,
        serves=draft.serves,
        provenance=draft.provenance,
        origin=draft.origin,
        derived_from=draft.derived_from,
    )
    async with session() as active:
        active.add(row)
        await active.flush()
        assert row.id is not None

        for position, line in enumerate(draft.lines):
            active.add(
                IngredientLineRow(
                    recipe_id=row.id,
                    position=position,
                    ingredient_id=line.ingredient_id,
                    magnitude=None if line.quantity is None else line.quantity.magnitude,
                    unit=None if line.quantity is None else line.quantity.unit,
                    preparation=line.preparation,
                    optional=line.optional,
                )
            )
        for position, step in enumerate(draft.steps):
            active.add(
                StepRow(
                    recipe_id=row.id,
                    position=position,
                    instruction=step.instruction,
                    duration_seconds=step.duration_seconds,
                    temperature_celsius=step.temperature_celsius,
                    attention=step.attention,
                )
            )
        try:
            await active.commit()
        except IntegrityError as exc:
            # A line pointing at an ingredient that is not in the registry (FR-9).
            raise IngredientNotRegistered(str(exc.orig)) from exc
        recipe_id = row.id

    # Indexed here rather than by each caller. Four paths store a recipe — authored,
    # imported from a document, imported from a page, seeded — and "remember to index it
    # too" is the shape of mistake that already cost the starter recipes their `serves`.
    # A recipe imported at ten o'clock should be findable at one minute past.
    await search.index_recipe(recipe_id)

    stored = await fetch(recipe_id, "en-GB")
    assert stored is not None, "a recipe just written must be readable"
    return stored


async def fetch(recipe_id: int, locale: str) -> Recipe | None:
    """A recipe whole, with ingredient names resolved for `locale`."""
    async with session() as active:
        row = await active.get(RecipeRow, recipe_id)
        if row is None or row.id is None:
            return None

        lines = await _lines_for(active, row.id, locale)
        steps = (
            await active.exec(
                select(StepRow)
                .where(col(StepRow.recipe_id) == row.id)
                .order_by(col(StepRow.position))
            )
        ).all()

    return Recipe(
        id=row.id,
        cook_id=row.cook_id,
        title=row.title,
        summary=row.summary,
        yield_quantity=Quantity(row.yield_magnitude, row.yield_unit),
        serves=row.serves,
        provenance=row.provenance,
        visibility=row.visibility,
        origin=row.origin,
        created_at=row.created_at,
        derived_from=row.derived_from,
        lines=lines,
        steps=[
            Step(
                id=step.id,
                instruction=step.instruction,
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
                attention=step.attention,
            )
            for step in steps
            if step.id is not None
        ],
    )


async def _lines_for(active: AsyncSession, recipe_id: int, locale: str) -> list[IngredientLine]:
    """Lines in written order, each with its registry entry resolved."""
    pairs = (
        await active.exec(
            select(IngredientLineRow, IngredientRow)
            .join(IngredientRow, col(IngredientLineRow.ingredient_id) == col(IngredientRow.id))
            .where(col(IngredientLineRow.recipe_id) == recipe_id)
            .order_by(col(IngredientLineRow.position))
        )
    ).all()

    # Resolved for the whole recipe at once. Leaving it off would give every line an
    # empty allergen set, which reads as "contains none" to anybody who does not also
    # check `classified` — the confusion ADR-006 exists to prevent.
    ingredient_ids = [entry.id for _, entry in pairs if entry.id is not None]
    classification = await allergens_within(active, ingredient_ids)
    names = await canonical_names_within(active, ingredient_ids, locale)

    lines: list[IngredientLine] = []
    for line, entry in pairs:
        if line.id is None or entry.id is None:
            continue
        allergens, classified = classification.get(entry.id, (frozenset(), False))
        lines.append(
            IngredientLine(
                id=line.id,
                ingredient=Ingredient(
                    id=entry.id,
                    slug=entry.slug,
                    kind=entry.kind,
                    name=names.get(entry.id, entry.slug),
                    density=entry.density,
                    origin=entry.origin,
                    allergens=allergens,
                    classified=classified,
                    piece_grams=entry.piece_grams,
                ),
                quantity=(
                    None
                    if line.magnitude is None or line.unit is None
                    else Quantity(line.magnitude, line.unit)
                ),
                preparation=line.preparation,
                optional=line.optional,
            )
        )
    return lines


async def list_for_cook(cook_id: int) -> list[RecipeSummary]:
    """A cook's own recipes. Private by default means private from other accounts."""
    async with session() as active:
        rows = (
            await active.exec(
                select(RecipeRow)
                .where(col(RecipeRow.cook_id) == cook_id)
                .order_by(col(RecipeRow.title))
            )
        ).all()
    return [
        RecipeSummary(
            id=row.id,
            title=row.title,
            summary=row.summary,
            yield_quantity=Quantity(row.yield_magnitude, row.yield_unit),
            serves=row.serves,
            visibility=row.visibility,
        )
        for row in rows
        if row.id is not None
    ]


async def steps_for_cook(cook_id: int) -> dict[int, list[Step]]:
    """Every step of every recipe this cook owns, in order, keyed by recipe.

    One query whatever the size of the collection, for the same reason `lines_to_judge` is
    three: how long a recipe takes belongs on the list a cook scans, and fetching each
    recipe whole to work it out would be several queries per row.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(StepRow)
                .join(RecipeRow, col(StepRow.recipe_id) == col(RecipeRow.id))
                .where(col(RecipeRow.cook_id) == cook_id)
                .order_by(col(StepRow.recipe_id), col(StepRow.position))
            )
        ).all()

    grouped: dict[int, list[Step]] = {}
    for row in rows:
        if row.id is None:
            continue
        grouped.setdefault(row.recipe_id, []).append(
            Step(
                id=row.id,
                instruction=row.instruction,
                duration_seconds=row.duration_seconds,
                temperature_celsius=row.temperature_celsius,
                attention=row.attention,
            )
        )
    return grouped


async def fetch_all_for_cook(cook_id: int, locale: str) -> list[Recipe]:
    """Every recipe a cook owns, whole. For export, which needs contents not summaries."""
    async with session() as active:
        rows = (
            await active.exec(
                select(RecipeRow)
                .where(col(RecipeRow.cook_id) == cook_id)
                .order_by(col(RecipeRow.title))
            )
        ).all()
        ids = [row.id for row in rows if row.id is not None]

    recipes = [await fetch(recipe_id, locale) for recipe_id in ids]
    return [recipe for recipe in recipes if recipe is not None]


async def lines_to_judge(cook_id: int, locale: str) -> list[JudgedLine]:
    """Every line of every recipe this cook owns, reduced to what a verdict needs.

    Three queries whatever the size of the collection. Fetching each recipe whole to put
    a badge on a list row would be several queries per row, on the screen a cook opens
    most often.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(IngredientLineRow, IngredientRow, RecipeRow)
                .join(IngredientRow, col(IngredientLineRow.ingredient_id) == col(IngredientRow.id))
                .join(RecipeRow, col(IngredientLineRow.recipe_id) == col(RecipeRow.id))
                .where(col(RecipeRow.cook_id) == cook_id)
                .order_by(col(IngredientLineRow.recipe_id), col(IngredientLineRow.position))
            )
        ).all()
        if not rows:
            return []

        ingredient_ids = [entry.id for _, entry, _ in rows if entry.id is not None]
        classification = await allergens_within(active, ingredient_ids)
        names = await canonical_names_within(active, ingredient_ids, locale)

    judged = []
    for line, entry, _ in rows:
        if entry.id is None:
            continue
        allergens, classified = classification.get(entry.id, (frozenset(), False))
        judged.append(
            JudgedLine(
                recipe_id=line.recipe_id,
                slug=entry.slug,
                name=names.get(entry.id, entry.slug),
                allergens=allergens,
                classified=classified,
                optional=line.optional,
            )
        )
    return judged


async def titles_of(recipe_ids: list[int]) -> dict[int, str]:
    """What these recipes are called, and nothing else.

    For naming the recipe a version was made from. Fetching the parent whole to print one
    line of it would be three queries for a link.
    """
    if not recipe_ids:
        return {}
    async with session() as active:
        rows = (await active.exec(select(RecipeRow).where(col(RecipeRow.id).in_(recipe_ids)))).all()
    return {row.id: row.title for row in rows if row.id is not None}
