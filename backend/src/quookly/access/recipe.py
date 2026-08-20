"""Access to recipes, in domain verbs.

A recipe is stored as three tables and returned as one whole thing, with its ingredient
lines resolved against the registry for the caller's locale. Callers deal in recipes;
rows and joins stay here.
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.ingredient import name_for
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


async def store(draft: RecipeDraft, cook_id: int) -> Recipe:
    """Persist a draft and return it whole."""
    row = RecipeRow(
        cook_id=cook_id,
        title=draft.title,
        summary=draft.summary,
        yield_magnitude=draft.yield_quantity.magnitude,
        yield_unit=draft.yield_quantity.unit,
        provenance=draft.provenance,
        origin=draft.origin,
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
                    magnitude=line.quantity.magnitude,
                    unit=line.quantity.unit,
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
                )
            )
        try:
            await active.commit()
        except IntegrityError as exc:
            # A line pointing at an ingredient that is not in the registry (FR-9).
            raise IngredientNotRegistered(str(exc.orig)) from exc
        recipe_id = row.id

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
        provenance=row.provenance,
        visibility=row.visibility,
        origin=row.origin,
        created_at=row.created_at,
        lines=lines,
        steps=[
            Step(
                id=step.id,
                instruction=step.instruction,
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
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

    lines: list[IngredientLine] = []
    for line, entry in pairs:
        if line.id is None or entry.id is None:
            continue
        lines.append(
            IngredientLine(
                id=line.id,
                ingredient=Ingredient(
                    id=entry.id,
                    slug=entry.slug,
                    kind=entry.kind,
                    name=await name_for(active, entry.id, locale, entry.slug),
                    density=entry.density,
                    origin=entry.origin,
                ),
                quantity=Quantity(line.magnitude, line.unit),
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
            visibility=row.visibility,
        )
        for row in rows
        if row.id is not None
    ]


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
