"""Access to recipes, in domain verbs.

A recipe is stored as three tables and returned as one whole thing, with its ingredient
lines resolved against the registry for the caller's locale. Callers deal in recipes;
rows and joins stay here.
"""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, delete, select
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
    Picture,
    Recipe,
    RecipeDraft,
    RecipeSummary,
    Step,
)
from quookly.contracts.suitability import JudgedLine


def _now() -> datetime:
    return datetime.now(UTC)


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
        language=draft.language,
    )
    async with session() as active:
        active.add(row)
        await active.flush()
        assert row.id is not None

        _write_contents(active, row.id, draft)
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


def _write_contents(active: AsyncSession, recipe_id: int, draft: RecipeDraft) -> None:
    """The lines and steps of a draft, in the order they were written.

    Shared by storing and restating so the two cannot come to disagree about what a
    recipe's contents are — `position` is what the whole reading order depends on, and
    two copies of the enumerate would be two chances to get it wrong.
    """
    for position, line in enumerate(draft.lines):
        active.add(
            IngredientLineRow(
                recipe_id=recipe_id,
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
                recipe_id=recipe_id,
                position=position,
                instruction=step.instruction,
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
                attention=step.attention,
            )
        )


async def restate(recipe_id: int, draft: RecipeDraft, cook_id: int) -> Recipe | None:
    """Replace a recipe's contents with how it should now read (ADR-059).

    Replacement rather than patching, because lines and steps are *ordered* collections:
    patching one would need an instruction for reordering, which is a language nobody
    asked for. Sending the recipe as it should read says the same thing with nothing left
    to interpret.

    **Provenance and origin are not rewritten.** Where a recipe came from is a fact about
    its arrival, not about who last touched it — an imported recipe that somebody corrects
    is still an imported recipe, and an upgrade must still know not to replace a cook's own
    (ADR-016).

    Another cook's recipe is absent rather than forbidden, the same rule reading one
    already follows: saying "forbidden" confirms it exists.
    """
    async with session() as active:
        row = await active.get(RecipeRow, recipe_id)
        if row is None or row.id is None or row.cook_id != cook_id:
            return None

        row.title = draft.title
        row.summary = draft.summary
        row.yield_magnitude = draft.yield_quantity.magnitude
        row.yield_unit = draft.yield_quantity.unit
        row.serves = draft.serves
        active.add(row)

        await active.exec(
            delete(IngredientLineRow).where(col(IngredientLineRow.recipe_id) == row.id)
        )
        await active.exec(delete(StepRow).where(col(StepRow.recipe_id) == row.id))
        await active.flush()
        _write_contents(active, row.id, draft)

        try:
            await active.commit()
        except IntegrityError as exc:
            raise IngredientNotRegistered(str(exc.orig)) from exc

    # What a recipe is findable by has just changed — its title, its summary and the
    # ingredients it names. The index is derived, so it follows rather than being told.
    await search.index_recipe(recipe_id)
    return await fetch(recipe_id, "en-GB")


async def archive(recipe_id: int, cook_id: int) -> bool:
    """Put a recipe away. Returns whether it was this cook's to put away.

    Not a delete. Plans, cooked meals and shopping ticks point at a recipe, and a cooked
    meal that lost its recipe is a hole in a history nobody can fill back in. An archived
    recipe leaves the cook's list and the search index and stays reachable by id.

    Idempotent: the useful question is whether it is put away, not how many times.
    """
    return await _set_archived(recipe_id, cook_id, _now())


async def restore(recipe_id: int, cook_id: int) -> bool:
    """Bring an archived recipe back into the list and the index."""
    return await _set_archived(recipe_id, cook_id, None)


async def illustrate(
    recipe_id: int, cook_id: int, media_id: str | None, description: str | None
) -> bool:
    """Put a picture on a recipe, or take the one it has off. Returns whether there was one.

    Both or neither, in one call: a media id without alt text is a picture some readers do
    not get, and separate setters would make that state reachable.

    Nothing deletes the file. A reference changing is not evidence that nobody wants the
    bytes — collecting what is no longer referred to is the CLI's, as it is for the
    Academy's pictures (ADR-057).
    """
    async with session() as active:
        row = await active.get(RecipeRow, recipe_id)
        if row is None or row.cook_id != cook_id or row.archived_at is not None:
            return False
        row.picture_media_id = media_id
        row.picture_description = description
        active.add(row)
        await active.commit()
        return True


async def _set_archived(recipe_id: int, cook_id: int, at: datetime | None) -> bool:
    async with session() as active:
        row = await active.get(RecipeRow, recipe_id)
        if row is None or row.id is None or row.cook_id != cook_id:
            return False
        row.archived_at = at
        active.add(row)
        await active.commit()

    if at is None:
        await search.index_recipe(recipe_id)
    else:
        # Out of the index rather than filtered at read time: a hit on a recipe somebody
        # has put away is the same nuisance as a hit on one that is gone.
        await search.remove(recipe_id)
    return True


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
        language=row.language,
        picture=(
            None
            if row.picture_media_id is None or row.picture_description is None
            else Picture(media_id=row.picture_media_id, description=row.picture_description)
        ),
        created_at=row.created_at,
        archived_at=row.archived_at,
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


async def list_for_cook(cook_id: int, *, archived: bool = False) -> list[RecipeSummary]:
    """A cook's own recipes. Private by default means private from other accounts.

    Archived ones are left out — that is what archiving is for — and asked for by name,
    because putting a recipe away should not be indistinguishable from losing it. One list
    or the other, never both: a cook looking at what they have and a cook looking through
    what they put away are asking different questions (ADR-059).
    """
    async with session() as active:
        put_away = col(RecipeRow.archived_at)
        rows = (
            await active.exec(
                select(RecipeRow)
                .where(
                    col(RecipeRow.cook_id) == cook_id,
                    put_away.is_not(None) if archived else put_away.is_(None),
                )
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
            picture=(
                None
                if row.picture_media_id is None or row.picture_description is None
                else Picture(media_id=row.picture_media_id, description=row.picture_description)
            ),
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
