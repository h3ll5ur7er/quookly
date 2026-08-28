"""Finding registry entries, for a client that needs to name one.

Thin, and deliberately still a manager. A route reading the registry directly would be a
client holding a use case, and the first thing that ever wants to change here — ranking
results, restricting them to what a cook has used, resolving against a locale other than
the request's — would have nowhere to go but into the route.
"""

from decimal import Decimal

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import search as search_index
from quookly.contracts.errors import NameAlreadyMeans
from quookly.contracts.ingredient import (
    UNSET,
    Allergen,
    CategoryView,
    DuplicateView,
    Ingredient,
    IngredientKind,
    IngredientView,
    Origin,
    RegistryEntryDetailView,
    RegistryEntryView,
    RegistryPageView,
    ResemblingView,
    Unset,
)
from quookly.contracts.matching import Resemblance
from quookly.engines import matching


async def search(term: str, cook_id: int, locale: str | None = None) -> list[IngredientView]:
    """Registry entries whose name matches `term`, for the caller to pick from.

    Searched in the cook's own language. A Swiss cook typing "Mehl" into "avoid a
    particular ingredient" should find flour — and a constraint that never resolved
    against anything is a constraint that silently never fires.
    """
    found = await registry.search(term, locale or await cook_access.locale_for(cook_id))
    return [
        IngredientView(id=entry.id, slug=entry.slug, name=entry.name, kind=entry.kind)
        for entry in found
    ]


async def categories(cook_id: int) -> list[CategoryView]:
    """The food tree, named as this cook reads it (ADR-067).

    Whole rather than paged. Twenty sections and a hundred groups is a list a screen holds,
    and a client that has it can put headings on anything it is showing — a shopping list,
    the registry, the Academy — without asking again for each.
    """
    found = await registry.categories(await cook_access.locale_for(cook_id))
    return [
        CategoryView(slug=one.slug, name=one.name, parent_slug=one.parent_slug) for one in found
    ]


async def browse(
    cook_id: int,
    *,
    term: str | None = None,
    origin: Origin | None = None,
    approved: bool | None = None,
    category: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> RegistryPageView:
    """A page of the registry, for a cook looking at it rather than picking from it.

    In the cook's own language, for the same reason `search` is: a registry a Swiss cook
    reads in English is a registry they cannot correct.

    `classified` travels beside `allergens` rather than being folded into it. An entry an
    import invented has an empty allergen set because nobody has looked, and one somebody
    checked has an empty set because there is nothing in it. Those are different facts and
    the boundary is where they are easiest to confuse (ADR-006).
    """
    page = await registry.browse(
        await cook_access.locale_for(cook_id),
        term=term,
        origin=origin,
        approved=approved,
        category=category,
        offset=offset,
        limit=limit,
    )
    return RegistryPageView(entries=[_viewed(entry) for entry in page.entries], total=page.total)


async def approve(slug: str) -> RegistryEntryView:
    """Record that an administrator has looked at this entry.

    Only that. It does not classify allergens and does not change the origin — an entry an
    import invented stays the cook's own after being approved, which is precisely why
    review needed a column of its own rather than being read off provenance (ADR-051).
    """
    return _viewed(await registry.approve(slug))


def _viewed(entry: Ingredient) -> RegistryEntryView:
    """One registry entry, as a client reads it.

    Shared so that browsing and approving cannot come to disagree about what an entry
    looks like — in particular about `classified`, where the two booleans are easy to
    confuse and the confusion is the one ADR-006 exists to prevent.
    """
    return RegistryEntryView(
        id=entry.id,
        slug=entry.slug,
        name=entry.name,
        kind=entry.kind,
        density=entry.density,
        piece_grams=entry.piece_grams,
        origin=entry.origin,
        allergens=sorted(entry.allergens, key=lambda allergen: allergen.value),
        classified=entry.classified,
        approved=entry.approved,
        category_slug=entry.category_slug,
    )


async def detail(slug: str) -> RegistryEntryDetailView | None:
    """One entry, whole, for a screen that corrects it."""
    found = await registry.detail(slug)
    if found is None:
        return None
    return RegistryEntryDetailView(
        entry=_viewed(found.entry),
        has_nutrition=bool(await registry.profiles_for([found.entry.id])),
        names=found.names,
    )


async def amend(
    slug: str,
    *,
    kind: IngredientKind | None = None,
    density: Decimal | None | Unset = UNSET,
    piece_grams: Decimal | None | Unset = UNSET,
) -> RegistryEntryView:
    """Correct the facts an import guessed at, and nothing else.

    Not the allergens and not the approval: three separate statements, kept separate so
    that making one cannot be mistaken for making another (ADR-006, ADR-051).
    """
    return _viewed(await registry.amend(slug, kind=kind, density=density, piece_grams=piece_grams))


async def classify(slug: str, allergens: list[Allergen]) -> RegistryEntryView | None:
    """Record what is in this ingredient, replacing any earlier answer.

    An empty list is a real answer — "somebody looked, and it contains none" — and is what
    separates a classified entry from an unexamined one (ADR-006). Its own use case rather
    than part of correcting, because a correction that happened to omit allergens would
    otherwise turn a known-milk entry into an unknown one.
    """
    await registry.classify(slug, frozenset(allergens))
    found = await registry.detail(slug)
    return None if found is None else _viewed(found.entry)


async def name(slug: str, locale: str, spellings: list[str]) -> RegistryEntryDetailView | None:
    """Teach the registry what this entry is called in another language.

    Additive: a spelling already recorded is left alone, and the names already there are
    not touched. An entry an import created is named in the language of the page it came
    from, and a Swiss cook adding the German for it should not have to destroy the English.

    Checked before writing rather than after failing. `name_in` swallows the unique-index
    violation and answers zero, which is right for start-up seeding — it runs every boot
    and must not care — but wrong for somebody pressing a button, who was told it worked.
    All the spellings are checked first, so a request carrying a good name and a taken one
    changes nothing rather than half-applying.
    """
    for spelling in spellings:
        held = await registry.resolve(spelling, locale)
        if held is not None and held.slug != slug:
            raise NameAlreadyMeans(spelling, held.slug)

    await registry.name_in(slug, locale, spellings)
    return await detail(slug)


async def rename(slug: str, locale: str, name: str) -> RegistryEntryDetailView | None:
    """Change what one language calls this entry.

    The old name is kept as a spelling rather than replaced: pages out there still use it,
    and an import that stopped resolving it would invent the duplicate this screen exists
    to clean up.
    """
    await registry.rename(slug, locale, name)
    return await detail(slug)


async def merge(*, keeper: str, loser: str) -> RegistryEntryDetailView | None:
    """Fold one entry into another, because they are the same food.

    The search index is rebuilt afterwards. It stores each recipe's ingredient *names* as
    text, so a merge changes what a recipe should be findable by — a recipe that said
    "plain flour" is now wheat flour and should answer to both. Rebuilt whole rather than
    per recipe: the index is derived, rebuilding is cheap at household scale, and merging
    is a rare deliberate act. Catching every affected recipe by hand is the kind of
    bookkeeping that is wrong once and then silently wrong for ever.
    """
    await registry.merge(keeper=keeper, loser=loser)
    await search_index.reindex()
    return await detail(keeper)


async def resembling(slug: str, cook_id: int, limit: int = 5) -> list[ResemblingView]:
    """Other entries this one might be the same food as.

    Read on demand rather than stored. A stored answer goes stale the moment somebody
    renames an entry, and the whole point of the report is to be looked at once and acted
    on.
    """
    found = await registry.detail(slug)
    if found is None:
        return []
    locale = await cook_access.locale_for(cook_id)
    entries = [entry for entry in await registry.named(locale) if entry.slug != slug]
    names = [name for spellings in found.names.values() for name in spellings]

    best: dict[str, tuple[Decimal, str, Resemblance]] = {}
    for name in names:
        for match in matching.resembling(name, entries, limit=limit):
            held = best.get(match.slug)
            if held is None or match.confidence > held[0]:
                best[match.slug] = (match.confidence, match.name, match.reason)

    ranked = sorted(best.items(), key=lambda one: (-one[1][0], one[0]))[:limit]
    ids = await registry.ids_by_slug([slug for slug, _ in ranked])
    carrying = {
        profile.ingredient_id for profile in await registry.profiles_for(list(ids.values()))
    }
    return [
        ResemblingView(
            slug=slug,
            name=name,
            confidence=confidence,
            reason=reason,
            carries_nutrition=ids.get(slug) in carrying,
        )
        for slug, (confidence, name, reason) in ranked
    ]


async def duplicates(cook_id: int, limit: int = 50) -> list[DuplicateView]:
    """Pairs across the whole registry that might be one ingredient.

    On demand. Against the shipped nine hundred entries this takes a few seconds, which is
    fine for something an administrator asks for and would not be fine on every request —
    if it ever wants running regularly it belongs in a CLI command and a cron job rather
    than in this process.
    """
    entries = await registry.named(await cook_access.locale_for(cook_id))
    return [
        DuplicateView(
            slug=pair.slug,
            other=pair.other,
            name=pair.name,
            other_name=pair.other_name,
            confidence=pair.confidence,
            reason=pair.reason,
        )
        for pair in matching.duplicates(entries, limit=limit)
    ]
