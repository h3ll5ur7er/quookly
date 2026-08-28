"""Access to the ingredient registry, in domain verbs."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import ColumnElement, case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.models import (
    AcademyPageRow,
    EaterConstraintRow,
    IngredientAllergenRow,
    IngredientCategoryNameRow,
    IngredientCategoryRow,
    IngredientLineRow,
    IngredientNameRow,
    IngredientRow,
    NutrientProfileRow,
    ShoppingTickRow,
    StockItemRow,
    WasteRow,
)
from quookly.contracts.errors import (
    IngredientAlreadyRegistered,
    IngredientNotRegistered,
    NameAlreadyMeans,
    NothingToMerge,
)
from quookly.contracts.ingredient import (
    UNSET,
    Allergen,
    Category,
    Ingredient,
    IngredientKind,
    Origin,
    RegistryEntryDetail,
    RegistryPage,
    Unset,
)
from quookly.contracts.matching import Named
from quookly.contracts.nutrition import NutrientProfile, NutritionSource
from quookly.utilities.text import fold, normalise

# The registry is seeded in English, so a Swiss instance must still resolve a seeded name
# until a translation for it exists. The fallback is to this one locale only: matching
# across languages would let `pain` resolve to bread for an English cook.
SOURCE_LOCALE = "en-GB"


def _to_contract(
    row: IngredientRow,
    name: str,
    allergens: frozenset[Allergen] = frozenset(),
    category_slug: str | None = None,
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
        approved=row.approved,
        piece_grams=row.piece_grams,
        category_id=row.category_id,
        category_slug=category_slug,
    )


async def _sitting(active: AsyncSession, row: IngredientRow) -> str | None:
    """The slug of the category one entry is in, if it is in one.

    A helper rather than a lookup at each call site, because there are seven of them and a
    field that some paths fill and others leave empty is a field nobody can trust.
    """
    if row.category_id is None:
        return None
    found = await active.get(IngredientCategoryRow, row.category_id)
    return None if found is None else found.slug


async def _all_sitting(active: AsyncSession, rows: Sequence[IngredientRow]) -> dict[int, str]:
    """Where each of many entries sits, in one query. Absent means uncategorised."""
    placed = {row.category_id for row in rows if row.category_id is not None}
    if not placed:
        return {}
    return {
        one.id: one.slug
        for one in (
            await active.exec(
                select(IngredientCategoryRow).where(col(IngredientCategoryRow.id).in_(placed))
            )
        ).all()
        if one.id is not None
    }


async def _category_id(active: AsyncSession, slug: str | None) -> int | None:
    """The id of a category by slug, or nothing.

    A slug this instance has never heard of resolves to nothing rather than raising. An
    entry naming an unknown category is still an entry, and losing the food would be a
    worse answer than losing where it sits.
    """
    if slug is None:
        return None
    row = (
        await active.exec(
            select(IngredientCategoryRow).where(col(IngredientCategoryRow.slug) == slug)
        )
    ).first()
    return None if row is None else row.id


async def add_category(
    *, slug: str, names: dict[str, str], parent_slug: str | None = None
) -> Category:
    """Record a category, or find the one already there.

    Repeatable, because seeding runs on every start-up — the same contract as registering
    an ingredient (ADR-016). An existing category keeps its parent and gains any name it
    did not have, so a build that adds a language teaches the tree that language without
    rewriting it.
    """
    async with session() as active:
        row = (
            await active.exec(
                select(IngredientCategoryRow).where(col(IngredientCategoryRow.slug) == slug)
            )
        ).first()
        if row is None:
            row = IngredientCategoryRow(
                slug=slug, parent_id=await _category_id(active, parent_slug)
            )
            active.add(row)
            await active.flush()
        assert row.id is not None

        known = {
            one.locale
            for one in (
                await active.exec(
                    select(IngredientCategoryNameRow).where(
                        col(IngredientCategoryNameRow.category_id) == row.id
                    )
                )
            ).all()
        }
        for locale, name in names.items():
            if locale not in known:
                active.add(IngredientCategoryNameRow(category_id=row.id, locale=locale, name=name))
        await active.commit()
        await active.refresh(row)
        return Category(
            id=row.id,
            slug=row.slug,
            name=names.get(SOURCE_LOCALE, next(iter(names.values()), row.slug)),
            parent_slug=parent_slug,
        )


async def categories(locale: str) -> list[Category]:
    """The whole tree, named as this reader reads it.

    Whole rather than paged: twenty sections and a hundred groups is a list a screen holds,
    and a client that has it can group anything it is showing without asking again.

    Named in the reader's locale where it has been, falling back to the language the
    registry was seeded in — the same fallback an ingredient's name uses, and for the same
    reason: a heading in the wrong language beats a heading that is a slug.
    """
    async with session() as active:
        rows = (
            await active.exec(select(IngredientCategoryRow).order_by(col(IngredientCategoryRow.id)))
        ).all()
        named = (
            await active.exec(
                select(IngredientCategoryNameRow).where(
                    col(IngredientCategoryNameRow.locale).in_([locale, SOURCE_LOCALE])
                )
            )
        ).all()

    by_id = {row.id: row for row in rows}
    wanted: dict[int, str] = {}
    for one in named:
        if one.locale == locale or one.category_id not in wanted:
            wanted[one.category_id] = one.name

    found: list[Category] = []
    for row in rows:
        assert row.id is not None
        parent = by_id.get(row.parent_id) if row.parent_id is not None else None
        found.append(
            Category(
                id=row.id,
                slug=row.slug,
                name=wanted.get(row.id, row.slug),
                parent_slug=None if parent is None else parent.slug,
            )
        )
    return found


async def register(
    *,
    slug: str,
    kind: IngredientKind,
    density: Decimal | None,
    names: dict[str, list[str]],
    origin: Origin = Origin.USER,
    allergens: frozenset[Allergen] | None = None,
    category_slug: str | None = None,
) -> Ingredient:
    """Add an entry. The first name given for a locale is that locale's canonical one.

    `allergens=None` means nobody has classified it — which is not the same as an empty
    set, and is the default because adding an ingredient is not classifying it.

    `category_slug` names where the food sits. One this instance has never heard of leaves
    the entry uncategorised rather than refusing it: losing the food is a worse answer than
    losing where it sits.
    """
    row = IngredientRow(
        slug=slug,
        kind=kind,
        density=density,
        origin=origin,
        allergens_classified=allergens is not None,
        # A seeded row is a published table this instance chose to ship; nobody signs off
        # nine hundred of those. Anything else was invented on somebody's behalf by an
        # import, and is usable straight away but unreviewed (ADR-051).
        approved=origin is Origin.SEED,
    )
    async with session() as active:
        row.category_id = await _category_id(active, category_slug)
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
        return _to_contract(
            row,
            canonical,
            allergens or frozenset(),
            category_slug if row.category_id is not None else None,
        )


async def name_in(slug: str, locale: str, spellings: list[str]) -> int:
    """Teach the registry what an entry is called in another language. Returns how many
    names were new.

    Additive and repeatable: a name already recorded is left alone, so start-up can run
    this every time without accumulating duplicates. It never touches the entry itself —
    a translation is a name, not a claim about density or allergens.
    """
    if not spellings:
        return 0
    async with session() as active:
        row = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug) == slug))
        ).first()
        if row is None or row.id is None:
            return 0

        existing = {
            name.normalised
            for name in (
                await active.exec(
                    select(IngredientNameRow).where(
                        col(IngredientNameRow.ingredient_id) == row.id,
                        col(IngredientNameRow.locale) == locale,
                    )
                )
            ).all()
        }

        added = 0
        for position, spelling in enumerate(spellings):
            wanted = normalise(spelling)
            if wanted in existing:
                continue
            active.add(
                IngredientNameRow(
                    ingredient_id=row.id,
                    locale=locale,
                    name=spelling,
                    normalised=wanted,
                    # The first spelling is what this language calls the thing; the rest
                    # are spellings a recipe might use.
                    is_canonical=position == 0 and not existing,
                )
            )
            existing.add(wanted)
            added += 1

        try:
            await active.commit()
        except IntegrityError:
            # Another entry already claims this spelling in this locale. The unique index
            # is on (locale, normalised) so a name means one thing per language, and the
            # first claim wins rather than the last.
            await active.rollback()
            return 0
        return added


@dataclass(frozen=True, slots=True)
class NewEntry:
    """One registry entry to add. `allergens=None` means nobody has classified it."""

    slug: str
    kind: IngredientKind
    density: Decimal | None
    names: dict[str, list[str]]
    allergens: frozenset[Allergen] | None = None
    #: Where the food sits. A slug this instance has never heard of leaves the entry
    #: uncategorised, exactly as in `register`.
    category_slug: str | None = None


async def register_many(entries: Sequence[NewEntry], origin: Origin = Origin.SEED) -> int:
    """Add many entries in one transaction. Returns how many were added.

    Written for the shipped registry of generic foods, which is nine hundred entries: one
    session each took nine seconds of a fresh instance's first start and made the test
    suite four times longer.

    Skips a slug that is already here rather than raising, because that is what every
    caller of this wants — seeding is additive and must not touch what it finds
    (ADR-016). A single `register` still raises, since adding one ingredient that already
    exists is a mistake worth hearing about.
    """
    if not entries:
        return 0

    async with session() as active:
        held = set(
            (
                await active.exec(
                    select(IngredientRow.slug).where(
                        col(IngredientRow.slug).in_([entry.slug for entry in entries])
                    )
                )
            ).all()
        )
        # A spelling means one ingredient per language, enforced by a unique index. Losing
        # that race would drop an entry silently, so the claim is settled here.
        claimed = {
            (row.locale, row.normalised)
            for row in (await active.exec(select(IngredientNameRow))).all()
        }
        # The whole tree once, rather than a lookup per entry: nine hundred entries is
        # nine hundred queries, which is what `register_many` exists to avoid.
        sections = {
            row.slug: row.id for row in (await active.exec(select(IngredientCategoryRow))).all()
        }

        rows: list[tuple[IngredientRow, NewEntry]] = []
        for entry in entries:
            if entry.slug in held:
                continue
            held.add(entry.slug)
            row = IngredientRow(
                slug=entry.slug,
                kind=entry.kind,
                density=entry.density,
                origin=origin,
                allergens_classified=entry.allergens is not None,
                # The same rule as `register`, and it has to be stated in both: the two
                # paths construct the row separately, and when only one of them knew, a
                # fresh instance opened with 864 of its 893 seeded entries queued for a
                # review nobody owed them (ADR-051).
                approved=origin is Origin.SEED,
                category_id=sections.get(entry.category_slug) if entry.category_slug else None,
            )
            active.add(row)
            rows.append((row, entry))

        await active.flush()

        for row, entry in rows:
            assert row.id is not None
            for locale, spellings in entry.names.items():
                position = 0
                for spelling in spellings:
                    wanted = normalise(spelling)
                    if (locale, wanted) in claimed:
                        continue
                    claimed.add((locale, wanted))
                    active.add(
                        IngredientNameRow(
                            ingredient_id=row.id,
                            locale=locale,
                            name=spelling,
                            normalised=wanted,
                            is_canonical=position == 0,
                        )
                    )
                    position += 1
            for allergen in entry.allergens or frozenset():
                active.add(IngredientAllergenRow(ingredient_id=row.id, allergen=allergen))

        await active.commit()
        return len(rows)


async def resolve(name: str, locale: str) -> Ingredient | None:
    """Find the ingredient a typed name refers to, or None.

    An unresolvable name is reported to the cook rather than invented (FR-9), which is
    why this returns absence instead of a best guess.

    A name whose accents were stripped is tried second — see `_folded_matches`. Second, not
    first: what somebody actually typed beats what it resembles.
    """
    wanted = normalise(name)
    async with session() as active:
        matches = list(
            (
                await active.exec(
                    select(IngredientNameRow).where(
                        col(IngredientNameRow.normalised) == wanted,
                        col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE]),
                    )
                )
            ).all()
        )
        if not matches:
            matches = await _folded_matches(active, wanted, locale)
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
        return _to_contract(
            row,
            display,
            frozenset(entry.allergen for entry in carried),
            await _sitting(active, row),
        )


async def _folded_matches(
    active: AsyncSession, wanted: str, locale: str
) -> list[IngredientNameRow]:
    """Names that match once accents are thrown away — but only if that is unambiguous.

    28% of the shipped registry's name rows carry diacritics and plenty of the web writes
    `creme fraiche`, which until now resolved to nothing and left an import inventing a
    duplicate beside the real entry.

    **Nothing is returned when more than one ingredient folds to the same string.** French
    `pêche` is a peach and `pèche` is fishing; they fold together and folding cannot say
    which was meant. Refusing leaves the import to record and report an unknown ingredient,
    which reads as *unknown* (ADR-029, ADR-006) — guessing would attach one food's
    allergens to another food's recipe.

    Read in Python rather than in SQL because SQLite has no unaccenting function and adding
    a folded column would mean re-normalising every stored name behind a unique index. It
    runs only when an exact match failed, over the names of two locales, at household
    scale.
    """
    spellings = (
        await active.exec(
            select(IngredientNameRow).where(
                col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE])
            )
        )
    ).all()
    folded = fold(wanted)
    resembling = [row for row in spellings if fold(row.normalised) == folded]
    if len({row.ingredient_id for row in resembling}) != 1:
        return []
    return resembling


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


async def canonical_names_within(
    active: AsyncSession, ingredient_ids: list[int], locale: str
) -> dict[int, str]:
    """Canonical names for many ingredients at once, in one query.

    The same fallback as `name_for` — the requested locale, then the locale the registry
    was seeded in — resolved for a whole recipe rather than a line at a time. An id with
    no name in either locale is absent, and the caller falls back to its slug.
    """
    if not ingredient_ids:
        return {}
    rows = (
        await active.exec(
            select(IngredientNameRow).where(
                col(IngredientNameRow.ingredient_id).in_(ingredient_ids),
                col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE]),
                col(IngredientNameRow.is_canonical).is_(True),
            )
        )
    ).all()

    resolved: dict[int, str] = {}
    for candidate in (locale, SOURCE_LOCALE):
        for row in rows:
            if row.locale == candidate and row.ingredient_id not in resolved:
                resolved[row.ingredient_id] = row.name
    return resolved


async def for_ids(ingredient_ids: list[int], locale: str) -> dict[int, Ingredient]:
    """Whole registry entries by id, named in `locale`.

    For a caller that holds ids and needs the entries behind them together — the pantry,
    whose lots carry an ingredient id and which has to show a name, a kind and a density
    at once. Names fall back the way `name_for` does, and to the slug when neither locale
    has one, so an entry is never nameless on screen.
    """
    if not ingredient_ids:
        return {}
    async with session() as active:
        rows = (
            await active.exec(
                select(IngredientRow).where(col(IngredientRow.id).in_(ingredient_ids))
            )
        ).all()
        names = await canonical_names_within(active, ingredient_ids, locale)
        carried = await allergens_within(active, ingredient_ids)
        # Where each of them sits, in one query. The shopping list reads this to put a
        # forty-item list into aisles (ADR-067).
        sitting = await _all_sitting(active, rows)
    return {
        row.id: _to_contract(
            row,
            names.get(row.id, row.slug),
            carried.get(row.id, (frozenset(), False))[0],
            sitting.get(row.category_id) if row.category_id is not None else None,
        )
        for row in rows
        if row.id is not None
    }


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


async def unplaced(slugs: list[str]) -> set[str]:
    """Which of these entries exist and sit in no category yet.

    Asked as one question rather than one per slug, and it is what makes seeding both
    repeatable and safe: an entry somebody filed themselves is not in the answer, so a
    later build cannot move it (ADR-016, ADR-067).
    """
    if not slugs:
        return set()
    async with session() as active:
        rows = (
            await active.exec(
                select(IngredientRow).where(
                    col(IngredientRow.slug).in_(slugs),
                    col(IngredientRow.category_id).is_(None),
                )
            )
        ).all()
    return {row.slug for row in rows}


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

    A term whose accents were stripped is folded in as well, but only when the exact
    search came back short — the common term costs nothing extra, and `creme` still finds
    `crème fraîche`. Unlike `resolve`, an ambiguous fold is **not** refused here: this
    returns a list somebody chooses from, so offering both `pêche` and `pèche` is the right
    answer and the cook decides.
    """
    wanted = normalise(term)
    if not wanted:
        return []

    async with session() as active:
        matches = list(
            (
                await active.exec(
                    select(IngredientNameRow)
                    .where(
                        col(IngredientNameRow.normalised).contains(wanted),
                        col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE]),
                    )
                    .limit(limit * 4)
                )
            ).all()
        )
        if len(matches) < limit:
            matches.extend(await _folded_containing(active, wanted, locale, matches))

        found: dict[int, Ingredient] = {}
        for match in matches:
            if match.ingredient_id in found:
                continue
            row = await active.get(IngredientRow, match.ingredient_id)
            if row is None or row.id is None:
                continue
            display = await name_for(active, row.id, locale, match.name)
            found[row.id] = _to_contract(row, display, category_slug=await _sitting(active, row))

    return sorted(found.values(), key=lambda entry: entry.name)[:limit]


async def browse(
    locale: str,
    *,
    term: str | None = None,
    origin: Origin | None = None,
    approved: bool | None = None,
    category: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> RegistryPage:
    """A page of the registry, ordered by the name the reader will see.

    Different from `search` in what it is for. `search` answers "which entry did the cook
    mean" and stops at the first handful; this answers "what is in here", which means it
    has to be complete, ordered and countable. The registry is the largest list in the
    app and the only one a cook currently cannot look at.

    Ordering is by display name with the id as a tiebreak, and names that open with a
    digit come after the ones that open with a letter. The tiebreak is not decoration: two
    entries sharing a name would otherwise be ordered differently on each query, and a
    page boundary landing between them would show one of them twice and the other never.
    The digit rule is not decoration either — the shipped table names its drinks by
    strength, so the registry's first screen was a wine list (G3).

    `category` narrows to one node of the food tree, and to a section takes everything in
    the groups under it (ADR-067).

    `term` matches any spelling, canonical or alias, in the reader's locale or the one the
    registry was seeded in — the same reach as `search`, so a name that resolves an import
    also finds its entry here. `origin` narrows to what was seeded or to what a cook's
    imports invented, which is the pile worth reviewing (ADR-016, ADR-029). `approved`
    narrows on review rather than on provenance — the more useful of the two, because an
    entry stays a cook's own after an admin has looked at it (ADR-051).
    """
    local_name = aliased(IngredientNameRow)
    seeded_name = aliased(IngredientNameRow)
    display = func.coalesce(local_name.name, seeded_name.name, IngredientRow.slug)
    # Names that open with a digit go last. The shipped table names its drinks by strength
    # — "11 vol% wine white", "12 vol% wine red" — and plain alphabetical order puts every
    # one of them in front of the letter A, so the registry's first screen was a wine list
    # (G3). Not a filter: they are real entries and they are still in the list.
    numbered = case((func.substr(display, 1, 1).between("0", "9"), 1), else_=0)

    narrowing: list[ColumnElement[bool]] = []
    if origin is not None:
        narrowing.append(col(IngredientRow.origin) == origin)
    if category is not None:
        # A section takes the groups under it. No food sits *on* a section — every leaf of
        # the published tree is a group — so narrowing to one and getting nothing back is
        # not the answer a cook asking about "Vegetables" wants.
        wanted_ids = (
            select(IngredientCategoryRow.id)
            .where(
                (col(IngredientCategoryRow.slug) == category)
                | col(IngredientCategoryRow.parent_id).in_(
                    select(IngredientCategoryRow.id).where(
                        col(IngredientCategoryRow.slug) == category
                    )
                )
            )
            .scalar_subquery()
        )
        narrowing.append(col(IngredientRow.category_id).in_(wanted_ids))
    if approved is not None:
        narrowing.append(col(IngredientRow.approved).is_(approved))
    wanted = normalise(term) if term else ""
    if wanted:
        # An `exists` rather than a join: an entry with two matching aliases is one entry,
        # and a join would page it as two.
        narrowing.append(
            select(IngredientNameRow.id)
            .where(
                col(IngredientNameRow.ingredient_id) == IngredientRow.id,
                col(IngredientNameRow.normalised).contains(wanted),
                col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE]),
            )
            .exists()
        )

    async with session() as active:
        total = (
            await active.exec(select(func.count()).select_from(IngredientRow).where(*narrowing))
        ).one()

        rows = (
            await active.exec(
                select(IngredientRow, display)
                .outerjoin(
                    local_name,
                    (col(local_name.ingredient_id) == IngredientRow.id)
                    & (col(local_name.locale) == locale)
                    & col(local_name.is_canonical).is_(True),
                )
                .outerjoin(
                    seeded_name,
                    (col(seeded_name.ingredient_id) == IngredientRow.id)
                    & (col(seeded_name.locale) == SOURCE_LOCALE)
                    & col(seeded_name.is_canonical).is_(True),
                )
                .where(*narrowing)
                .order_by(numbered, display, col(IngredientRow.id))
                .offset(offset)
                .limit(limit)
            )
        ).all()

        found = [(row, str(name)) for row, name in rows if row.id is not None]
        allergens = await allergens_within(active, [row.id for row, _ in found if row.id])
        # Where each of them sits, in one query rather than one per row. The slug rather
        # than the name: a client that has the tree can name it, and a screen grouping
        # nine hundred entries needs the key to group on, not a hundred repeated strings.
        sitting = await _all_sitting(active, [row for row, _ in found])

    return RegistryPage(
        entries=[
            _to_contract(
                row,
                name,
                allergens.get(row.id, (frozenset(), False))[0],
                sitting.get(row.category_id) if row.category_id is not None else None,
            )
            for row, name in found
            if row.id is not None
        ],
        total=total,
    )


async def _restated(active: AsyncSession, row: IngredientRow, slug: str) -> Ingredient:
    """A row as it now stands, after a write, with its allergens.

    Shared by every write that hands the entry back. Building the contract from the row
    alone omits them, and an entry that has been classified then comes back as
    `classified=True` with an empty set — which does not read as "unknown", it reads as
    "somebody looked and there is nothing in it". That is a false clean bill, and it is
    the exact failure ADR-006 exists to prevent, so no write path is allowed its own
    version of this.

    The refresh before it matters too: the database quantises a density to four decimal
    places, and returning the unrounded value in memory means a caller is told something
    different from what a subsequent read gives them.
    """
    assert row.id is not None, "a persisted ingredient always has an id"
    carried = await allergens_within(active, [row.id])
    allergens, _ = carried.get(row.id, (frozenset(), False))
    return _to_contract(
        row,
        await name_for(active, row.id, SOURCE_LOCALE, slug),
        allergens,
        await _sitting(active, row),
    )


async def named(locale: str) -> list[Named]:
    """Every entry with every spelling it answers to, for the matcher to compare.

    Reference data for a rule engine, which is why it comes out as a plain list rather
    than being reached for: `MatchingEngine` reads no database, so the whole registry
    arrives as an argument.

    One locale at a time — the reader's, falling back to the one the registry was seeded
    in, the same reach as every other read here. Comparing an English name against a German
    one would find nothing but coincidence.
    """
    async with session() as active:
        spellings = (
            await active.exec(
                select(IngredientRow, IngredientNameRow)
                .join(
                    IngredientNameRow,
                    onclause=col(IngredientNameRow.ingredient_id) == IngredientRow.id,
                )
                .where(col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE]))
            )
        ).all()

    gathered: dict[str, list[str]] = {}
    for row, spelling in spellings:
        gathered.setdefault(row.slug, []).append(spelling.name)
    return [Named(slug=slug, names=tuple(names)) for slug, names in sorted(gathered.items())]


async def detail(slug: str) -> RegistryEntryDetail | None:
    """One entry with every name it answers to, for a screen that corrects it.

    `resolve` answers "which entry is this name" and `browse` answers "what is in the
    registry"; neither carries what an entry is called in the *other* languages. For an
    entry an import created that is most of what there is to correct — it arrives named
    only in the language of the page it came from.
    """
    async with session() as active:
        row = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug) == slug))
        ).first()
        if row is None or row.id is None:
            return None

        spellings = (
            await active.exec(
                select(IngredientNameRow)
                .where(col(IngredientNameRow.ingredient_id) == row.id)
                .order_by(col(IngredientNameRow.is_canonical).desc(), col(IngredientNameRow.id))
            )
        ).all()

        carried = await allergens_within(active, [row.id])
        allergens, _ = carried.get(row.id, (frozenset(), False))

        names: dict[str, list[str]] = {}
        for spelling in spellings:
            names.setdefault(spelling.locale, []).append(spelling.name)

        display = await name_for(active, row.id, SOURCE_LOCALE, slug)
        sitting = await _sitting(active, row)

    return RegistryEntryDetail(entry=_to_contract(row, display, allergens, sitting), names=names)


async def rename(slug: str, locale: str, name: str) -> Ingredient:
    """Change what one language calls this entry.

    Different from `name_in`, which is additive and only ever sets the canonical name for
    a locale that had none. What an import decided to call something was otherwise
    permanent, and for the entries an import invents that is the field most likely to be
    wrong: the name recorded is whatever the page wrote.

    **The old name is demoted, not deleted.** Pages and documents out there still say it,
    and an import that stopped resolving it would go straight back to inventing a
    duplicate — the thing this screen exists to clean up. It stays as a spelling; only
    which one is canonical changes.

    Refused if another entry already means this in this locale, for the same reason
    `IngredientManager.name` refuses: a name means one thing per language, or a recipe
    saying it could not be resolved to one ingredient.
    """
    wanted = normalise(name)
    async with session() as active:
        row = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug) == slug))
        ).first()
        if row is None or row.id is None:
            raise IngredientNotRegistered(slug)

        claimed = (
            await active.exec(
                select(IngredientNameRow).where(
                    col(IngredientNameRow.locale) == locale,
                    col(IngredientNameRow.normalised) == wanted,
                )
            )
        ).first()
        if claimed is not None and claimed.ingredient_id != row.id:
            holder = await active.get(IngredientRow, claimed.ingredient_id)
            raise NameAlreadyMeans(name, holder.slug if holder is not None else "another entry")

        spellings = (
            await active.exec(
                select(IngredientNameRow).where(
                    col(IngredientNameRow.ingredient_id) == row.id,
                    col(IngredientNameRow.locale) == locale,
                )
            )
        ).all()
        for spelling in spellings:
            spelling.is_canonical = spelling.normalised == wanted
            active.add(spelling)

        if claimed is None:
            active.add(
                IngredientNameRow(
                    ingredient_id=row.id,
                    locale=locale,
                    name=name,
                    normalised=wanted,
                    is_canonical=True,
                )
            )

        await active.commit()
        await active.refresh(row)

        return await _restated(active, row, slug)


async def amend(
    slug: str,
    *,
    kind: IngredientKind | None = None,
    density: Decimal | None | Unset = UNSET,
    piece_grams: Decimal | None | Unset = UNSET,
    category_slug: str | None | Unset = UNSET,
) -> Ingredient:
    """Correct the facts an import guesses at, and where the food sits.

    Only those. It does **not** classify allergens — fixing a density is not looking
    inside the food (ADR-006) — and it does not approve the entry, because "this row is
    right" and "I have reviewed this row" are two statements and an admin correcting one
    field has not necessarily finished with the rest (ADR-051).

    A field that was not mentioned is left alone. `density` and `piece_grams` take the
    `UNSET` sentinel rather than defaulting to `None` because absent is a real answer for
    both: an ingredient nobody has weighed *has* no piece weight, and a wrong density is
    worse than none. Without the sentinel, correcting the kind would wipe the density
    beside it.

    `category_slug` takes the sentinel for the same reason: filed in the wrong aisle is
    worse than filed in none, so clearing one is a real correction — and a form that saves
    a density must not unplace the food beside it (ADR-067). A slug this instance does not
    know leaves the placement alone rather than clearing it: an unknown category is not
    evidence about where the food belongs.

    `kind` needs no sentinel: an entry always has one, so `None` can only mean "leave it".
    """
    async with session() as active:
        row = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug) == slug))
        ).first()
        if row is None or row.id is None:
            raise IngredientNotRegistered(slug)

        if kind is not None:
            row.kind = kind
        if not isinstance(density, Unset):
            row.density = density
        if not isinstance(piece_grams, Unset):
            row.piece_grams = piece_grams
        if not isinstance(category_slug, Unset):
            wanted = await _category_id(active, category_slug)
            if category_slug is None or wanted is not None:
                row.category_id = wanted

        active.add(row)
        await active.commit()
        await active.refresh(row)

        return await _restated(active, row, slug)


async def merge(*, keeper: str, loser: str) -> Ingredient:
    """Fold one registry entry into another, because they are the same food.

    The operation the registry screen exists for. An import that created `plain flour`
    beside a registry that already had `wheat flour` split one ingredient in two, and every
    allergen and nutrition fact then answers for half a kitchen.

    Three things about it are load-bearing.

    **The loser's names survive as spellings of the keeper.** That is the difference
    between merging and deleting: a page that says "plain flour" has to keep resolving, or
    the next import invents the duplicate all over again.

    **Allergens are the union, and one examination counts for both.** Two entries that
    disagree are two examinations of one food, and the merge takes the cautious reading —
    it can add an allergen and can never remove one (ADR-006). An unexamined side adds no
    information: the food was examined, whichever row somebody wrote it on.

    **An eater's constraints are repointed by slug.** `eater_constraint.ingredient_slug` is
    text with no foreign key, deliberately, so that avoiding coriander works whether or not
    the registry has heard of it. The cost is that nothing in the database protects it here:
    an eater avoiding the loser would silently stop being warned. That is an allergy that
    stops firing and says nothing, and it is the reason this function is written as one
    transaction rather than a sequence of tidy little verbs.

    The keeper's own facts win where it has them and are filled from the loser where it does
    not — an admin merging *into* an entry has chosen it as the truthful one, but a figure
    on either side still describes the same food.
    """
    if normalise(keeper) == normalise(loser):
        raise NothingToMerge(keeper)

    async with session() as active:
        rows = {
            row.slug: row
            for row in (
                await active.exec(
                    select(IngredientRow).where(col(IngredientRow.slug).in_([keeper, loser]))
                )
            ).all()
        }
        surviving = rows.get(keeper)
        going = rows.get(loser)
        if surviving is None or surviving.id is None:
            raise IngredientNotRegistered(keeper)
        if going is None or going.id is None:
            raise IngredientNotRegistered(loser)

        # --- what the entry knows about itself -------------------------------------------
        if surviving.density is None:
            surviving.density = going.density
        if surviving.piece_grams is None:
            surviving.piece_grams = going.piece_grams
        surviving.allergens_classified = (
            surviving.allergens_classified or going.allergens_classified
        )

        # --- the allergens, deduplicated: `(ingredient_id, allergen)` is unique -----------
        held = {
            entry.allergen
            for entry in (
                await active.exec(
                    select(IngredientAllergenRow).where(
                        col(IngredientAllergenRow.ingredient_id) == surviving.id
                    )
                )
            ).all()
        }
        for entry in (
            await active.exec(
                select(IngredientAllergenRow).where(
                    col(IngredientAllergenRow.ingredient_id) == going.id
                )
            )
        ).all():
            if entry.allergen in held:
                await active.delete(entry)
            else:
                entry.ingredient_id = surviving.id
                active.add(entry)
                held.add(entry.allergen)

        # --- the names: `(locale, normalised)` is unique ----------------------------------
        spoken = {
            (name.locale, name.normalised)
            for name in (
                await active.exec(
                    select(IngredientNameRow).where(
                        col(IngredientNameRow.ingredient_id) == surviving.id
                    )
                )
            ).all()
        }
        for name in (
            await active.exec(
                select(IngredientNameRow).where(col(IngredientNameRow.ingredient_id) == going.id)
            )
        ).all():
            if (name.locale, name.normalised) in spoken:
                await active.delete(name)
                continue
            name.ingredient_id = surviving.id
            # Demoted on the way across: the keeper already has a name in this language, and
            # two canonical names for one locale is not a state `name_for` can read.
            name.is_canonical = False
            active.add(name)
            spoken.add((name.locale, name.normalised))

        # --- the figures: `(ingredient_id, source, nutrient)` is unique -------------------
        published = {
            (profile.source, profile.nutrient)
            for profile in (
                await active.exec(
                    select(NutrientProfileRow).where(
                        col(NutrientProfileRow.ingredient_id) == surviving.id
                    )
                )
            ).all()
        }
        for profile in (
            await active.exec(
                select(NutrientProfileRow).where(col(NutrientProfileRow.ingredient_id) == going.id)
            )
        ).all():
            if (profile.source, profile.nutrient) in published:
                await active.delete(profile)
                continue
            profile.ingredient_id = surviving.id
            active.add(profile)
            published.add((profile.source, profile.nutrient))

        # --- everything that merely points at it ------------------------------------------
        # `AcademyPageRow` is the ninth relationship, and the reason it is listed rather
        # than left to the foreign key: a page about a food that was merged away is a page
        # about nothing, and several pages naming one entry is not a conflict — nothing
        # computes on which page is the page (ADR-058, ADR-061).
        for pointing in (IngredientLineRow, StockItemRow, WasteRow, AcademyPageRow):
            for row in (
                await active.exec(select(pointing).where(col(pointing.ingredient_id) == going.id))
            ).all():
                row.ingredient_id = surviving.id
                active.add(row)

        # `(plan_id, ingredient_id)` is unique: a plan that ticked both lines has ticked one
        # ingredient twice, and the merge leaves it ticked once.
        ticked = {
            tick.plan_id
            for tick in (
                await active.exec(
                    select(ShoppingTickRow).where(
                        col(ShoppingTickRow.ingredient_id) == surviving.id
                    )
                )
            ).all()
        }
        for tick in (
            await active.exec(
                select(ShoppingTickRow).where(col(ShoppingTickRow.ingredient_id) == going.id)
            )
        ).all():
            if tick.plan_id in ticked:
                await active.delete(tick)
                continue
            tick.ingredient_id = surviving.id
            active.add(tick)
            ticked.add(tick.plan_id)

        # --- and the one nothing protects --------------------------------------------------
        for constraint in (
            await active.exec(
                select(EaterConstraintRow).where(col(EaterConstraintRow.ingredient_slug) == loser)
            )
        ).all():
            constraint.ingredient_slug = keeper
            active.add(constraint)

        await active.delete(going)
        await active.commit()
        await active.refresh(surviving)

        return await _restated(active, surviving, keeper)


async def approve(slug: str) -> Ingredient:
    """Record that somebody has reviewed this entry.

    Only the review. Approving does **not** classify allergens and does not change the
    origin: an admin saying "this entry is fine" has not said what is inside the
    ingredient (ADR-006), and the row stays the cook's own so an upgrade will not replace
    it (ADR-016).

    Idempotent, because the useful question is whether the entry has been looked at, not
    how many times.
    """
    async with session() as active:
        row = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug) == slug))
        ).first()
        if row is None or row.id is None:
            raise IngredientNotRegistered(slug)

        row.approved = True
        active.add(row)
        await active.commit()
        await active.refresh(row)

        return await _restated(active, row, slug)


async def place_in_category(slug: str, category_slug: str | None) -> Ingredient:
    """Say where a food sits, or stop saying.

    Correctable, which is the point of a tree over two columns: the published table places
    the nine hundred it shipped, and everything a household adds after that is placed by a
    person (ADR-067). A category this instance has never heard of clears the placement
    rather than raising — the same rule `register` follows, for the same reason.
    """
    async with session() as active:
        row = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug) == slug))
        ).first()
        if row is None or row.id is None:
            raise IngredientNotRegistered(slug)

        row.category_id = await _category_id(active, category_slug)
        active.add(row)
        await active.commit()
        await active.refresh(row)

        return await _restated(active, row, slug)


async def _folded_containing(
    active: AsyncSession, wanted: str, locale: str, already: list[IngredientNameRow]
) -> list[IngredientNameRow]:
    """Names containing the term once accents are gone, minus what was already found.

    Read in Python for the same reason `_folded_matches` is: SQLite cannot unaccent, and a
    folded column would mean re-normalising every stored name behind a unique index. Only
    reached when the exact search came back short, so a term that is doing fine never pays
    for it.
    """
    spellings = (
        await active.exec(
            select(IngredientNameRow).where(
                col(IngredientNameRow.locale).in_([locale, SOURCE_LOCALE])
            )
        )
    ).all()
    seen = {row.id for row in already}
    folded = fold(wanted)
    return [row for row in spellings if row.id not in seen and folded in fold(row.normalised)]


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
        return await allergens_within(active, ingredient_ids)


async def allergens_within(
    active: AsyncSession, ingredient_ids: list[int]
) -> dict[int, tuple[frozenset[Allergen], bool]]:
    """The same, inside a transaction the caller already has open.

    A recipe resolves its lines and their classification in one read rather than opening
    a second connection partway through the first — which, on SQLite, is a second file
    handle to the same database in the middle of a transaction.
    """
    if not ingredient_ids:
        return {}
    rows = (
        await active.exec(select(IngredientRow).where(col(IngredientRow.id).in_(ingredient_ids)))
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


async def profiles_for(ingredient_ids: list[int]) -> list[NutrientProfile]:
    """Every published figure held for these ingredients, from every source.

    All of them, not the preferred one: which table answers is decided against the
    instance's configured order by `NutritionEngine`, so that a change of order is a
    setting rather than a re-import (ADR-045). Choosing here would put the most volatile
    judgement in the least volatile place.
    """
    if not ingredient_ids:
        return []
    async with session() as active:
        rows = (
            await active.exec(
                select(NutrientProfileRow)
                .where(col(NutrientProfileRow.ingredient_id).in_(ingredient_ids))
                .order_by(col(NutrientProfileRow.ingredient_id), col(NutrientProfileRow.source))
            )
        ).all()

    gathered: dict[tuple[int, NutritionSource], NutrientProfile] = {}
    for row in rows:
        key = (row.ingredient_id, row.source)
        if key not in gathered:
            gathered[key] = NutrientProfile(
                ingredient_id=row.ingredient_id,
                source=row.source,
                reference=row.reference,
                amounts={},
            )
        gathered[key].amounts[row.nutrient] = row.amount
    return list(gathered.values())


async def record_profiles(profiles: Sequence[NutrientProfile]) -> int:
    """Restate what one table says about many ingredients, in one transaction.

    The same operation as `record_profile` and the same wholesale-replacement rule; what
    differs is that it is not paid nine hundred times. Seeding restates every shipped
    figure on every start-up, deliberately — a refreshed table is a corrected table — and
    once the registry held the whole Swiss database that cost nine seconds of every boot.

    Grouped by source, because that is the unit the replacement is defined over: a source
    withdrawing a nutrient must lose it here, and nothing another source published may go
    with it.
    """
    if not profiles:
        return 0

    by_source: dict[NutritionSource, list[NutrientProfile]] = {}
    for profile in profiles:
        by_source.setdefault(profile.source, []).append(profile)

    written = 0
    async with session() as active:
        for source, holding in by_source.items():
            await active.exec(
                delete(NutrientProfileRow)
                .where(col(NutrientProfileRow.source) == source)
                .where(
                    col(NutrientProfileRow.ingredient_id).in_(
                        [profile.ingredient_id for profile in holding]
                    )
                )
            )
            # Flushed before the inserts, or they race the delete into the unique index
            # and a second seeding fails on figures it is only restating.
            await active.flush()
            for profile in holding:
                for nutrient, amount in profile.amounts.items():
                    active.add(
                        NutrientProfileRow(
                            ingredient_id=profile.ingredient_id,
                            source=source,
                            nutrient=nutrient,
                            amount=amount,
                            reference=profile.reference,
                        )
                    )
                written += 1
        await active.commit()
    return written


async def record_profile(profile: NutrientProfile) -> None:
    """Write down what one table says about one ingredient, replacing what it said before.

    Restated wholesale rather than merged, for the same reason a plan's reservations are
    (ADR-038): a nutrient that has been *withdrawn* from a published table must disappear
    here, and a merge would leave it behind for ever.
    """
    async with session() as active:
        held = (
            await active.exec(
                select(NutrientProfileRow)
                .where(col(NutrientProfileRow.ingredient_id) == profile.ingredient_id)
                .where(col(NutrientProfileRow.source) == profile.source)
            )
        ).all()
        for row in held:
            await active.delete(row)
        # Flushed before the new rows go in, or the insert races the delete into the
        # unique index and a second seeding fails on figures it is only restating.
        await active.flush()
        for nutrient, amount in profile.amounts.items():
            active.add(
                NutrientProfileRow(
                    ingredient_id=profile.ingredient_id,
                    source=profile.source,
                    nutrient=nutrient,
                    amount=amount,
                    reference=profile.reference,
                )
            )
        await active.commit()


async def weigh_pieces(slug: str, grams: Decimal | None) -> None:
    """Say what one of a countable ingredient weighs, so it can be counted (UC-2.3)."""
    async with session() as active:
        row = (
            await active.exec(select(IngredientRow).where(col(IngredientRow.slug) == slug))
        ).first()
        if row is None:
            return
        row.piece_grams = grams
        active.add(row)
        await active.commit()
