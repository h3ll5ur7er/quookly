"""Access to the ingredient registry, in domain verbs."""

import re
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.models import IngredientAllergenRow, IngredientNameRow, IngredientRow
from quookly.contracts.errors import IngredientAlreadyRegistered
from quookly.contracts.ingredient import Allergen, Ingredient, IngredientKind, Origin

# The registry is seeded in English, so a Swiss instance must still resolve a seeded name
# until a translation for it exists. The fallback is to this one locale only: matching
# across languages would let `pain` resolve to bread for an English cook.
SOURCE_LOCALE = "en-GB"

_WHITESPACE = re.compile(r"\s+")


def normalise(name: str) -> str:
    """Fold the variations of a typed name that mean the same ingredient."""
    return _WHITESPACE.sub(" ", name.strip().lower())


def _to_contract(
    row: IngredientRow, name: str, allergens: frozenset[Allergen] = frozenset()
) -> Ingredient:
    assert row.id is not None, "a persisted ingredient always has an id"
    return Ingredient(
        id=row.id,
        slug=row.slug,
        kind=row.kind,
        name=name,
        density=row.density,
        origin=row.origin,
        allergens=allergens,
        classified=row.allergens_classified,
    )


async def register(
    *,
    slug: str,
    kind: IngredientKind,
    density: Decimal | None,
    names: dict[str, list[str]],
    origin: Origin = Origin.USER,
    allergens: frozenset[Allergen] | None = None,
) -> Ingredient:
    """Add an entry. The first name given for a locale is that locale's canonical one.

    `allergens=None` means nobody has classified it — which is not the same as an empty
    set, and is the default because adding an ingredient is not classifying it.
    """
    row = IngredientRow(
        slug=slug,
        kind=kind,
        density=density,
        origin=origin,
        allergens_classified=allergens is not None,
    )
    async with session() as active:
        active.add(row)
        try:
            await active.flush()
        except IntegrityError as exc:
            raise IngredientAlreadyRegistered(slug) from exc

        assert row.id is not None
        for locale, spellings in names.items():
            for position, spelling in enumerate(spellings):
                active.add(
                    IngredientNameRow(
                        ingredient_id=row.id,
                        locale=locale,
                        name=spelling,
                        normalised=normalise(spelling),
                        is_canonical=position == 0,
                    )
                )
        for allergen in allergens or frozenset():
            active.add(IngredientAllergenRow(ingredient_id=row.id, allergen=allergen))

        try:
            await active.commit()
        except IntegrityError as exc:
            raise IngredientAlreadyRegistered(slug) from exc
        await active.refresh(row)
        canonical = names.get(SOURCE_LOCALE, next(iter(names.values())))[0]
        return _to_contract(row, canonical, allergens or frozenset())


async def resolve(name: str, locale: str) -> Ingredient | None:
    """Find the ingredient a typed name refers to, or None.

    An unresolvable name is reported to the cook rather than invented (FR-9), which is
    why this returns absence instead of a best guess.
    """
    wanted = normalise(name)
    async with session() as active:
        matches = (
            await active.exec(
                select(IngredientNameRow).where(
                    col(IngredientNameRow.normalised) == wanted,
                    col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE]),
                )
            )
        ).all()
        if not matches:
            return None

        # A name in the asked-for locale beats the English fallback.
        matched = next((m for m in matches if m.locale == locale), matches[0])
        row = await active.get(IngredientRow, matched.ingredient_id)
        if row is None:
            return None

        display = await name_for(active, matched.ingredient_id, locale, matched.name)
        carried = (
            await active.exec(
                select(IngredientAllergenRow).where(
                    col(IngredientAllergenRow.ingredient_id) == matched.ingredient_id
                )
            )
        ).all()
        return _to_contract(row, display, frozenset(entry.allergen for entry in carried))


async def name_for(active: AsyncSession, ingredient_id: int, locale: str, fallback: str) -> str:
    """What to call this ingredient in `locale` — the canonical name, not an alias.

    Shared with `recipe` access, which resolves a line's ingredient the same way.
    """
    for candidate_locale in (locale, SOURCE_LOCALE):
        canonical = (
            await active.exec(
                select(IngredientNameRow).where(
                    col(IngredientNameRow.ingredient_id) == ingredient_id,
                    col(IngredientNameRow.locale) == candidate_locale,
                    col(IngredientNameRow.is_canonical).is_(True),
                )
            )
        ).first()
        if canonical is not None:
            return str(canonical.name)
    return fallback


async def densities_for(ingredient_ids: list[int]) -> dict[int, Decimal | None]:
    """Densities for a whole recipe at once, rather than one query per line."""
    if not ingredient_ids:
        return {}
    async with session() as active:
        rows = (
            await active.exec(
                select(IngredientRow).where(col(IngredientRow.id).in_(ingredient_ids))
            )
        ).all()
    return {row.id: row.density for row in rows if row.id is not None}


async def slugs_present(slugs: list[str]) -> set[str]:
    """Which of these slugs this instance already knows."""
    if not slugs:
        return set()
    async with session() as active:
        rows = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug).in_(slugs)))
        ).all()
    return {row.slug for row in rows}


async def ids_by_slug(slugs: list[str]) -> dict[str, int]:
    """Map slugs to this instance's ids. A document refers by slug; storage needs ids."""
    if not slugs:
        return {}
    async with session() as active:
        rows = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug).in_(slugs)))
        ).all()
    return {row.slug: row.id for row in rows if row.id is not None}


async def search(term: str, locale: str, limit: int = 20) -> list[Ingredient]:
    """Registry entries whose name contains `term`, for choosing one.

    Matches on the normalised name, so a cook typing into a field is not typing a database
    key. Results are the canonical name for their locale, deduplicated: matching two
    aliases of one ingredient should offer it once.
    """
    wanted = normalise(term)
    if not wanted:
        return []

    async with session() as active:
        matches = (
            await active.exec(
                select(IngredientNameRow)
                .where(
                    col(IngredientNameRow.normalised).contains(wanted),
                    col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE]),
                )
                .limit(limit * 4)
            )
        ).all()

        found: dict[int, Ingredient] = {}
        for match in matches:
            if match.ingredient_id in found:
                continue
            row = await active.get(IngredientRow, match.ingredient_id)
            if row is None or row.id is None:
                continue
            display = await name_for(active, row.id, locale, match.name)
            found[row.id] = _to_contract(row, display)

    return sorted(found.values(), key=lambda entry: entry.name)[:limit]


async def classify(slug: str, allergens: frozenset[Allergen]) -> None:
    """Record which allergens an ingredient contains, replacing any earlier answer.

    An empty set is a real answer — "somebody looked, and it contains none" — and is what
    separates a classified ingredient from an unexamined one.
    """
    async with session() as active:
        row = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug) == slug))
        ).first()
        if row is None or row.id is None:
            return

        existing = (
            await active.exec(
                select(IngredientAllergenRow).where(
                    col(IngredientAllergenRow.ingredient_id) == row.id
                )
            )
        ).all()
        for entry in existing:
            await active.delete(entry)
        for allergen in allergens:
            active.add(IngredientAllergenRow(ingredient_id=row.id, allergen=allergen))

        row.allergens_classified = True
        active.add(row)
        await active.commit()


async def allergens_for(
    ingredient_ids: list[int],
) -> dict[int, tuple[frozenset[Allergen], bool]]:
    """Allergens and classification for a whole recipe at once.

    One query for a verdict rather than one per ingredient, and the boolean travels with
    the set so a caller cannot accidentally read silence as safety.
    """
    if not ingredient_ids:
        return {}
    async with session() as active:
        rows = (
            await active.exec(
                select(IngredientRow).where(col(IngredientRow.id).in_(ingredient_ids))
            )
        ).all()
        carried = (
            await active.exec(
                select(IngredientAllergenRow).where(
                    col(IngredientAllergenRow.ingredient_id).in_(ingredient_ids)
                )
            )
        ).all()

    by_ingredient: dict[int, set[Allergen]] = {}
    for entry in carried:
        by_ingredient.setdefault(entry.ingredient_id, set()).add(entry.allergen)

    return {
        row.id: (frozenset(by_ingredient.get(row.id, set())), row.allergens_classified)
        for row in rows
        if row.id is not None
    }
