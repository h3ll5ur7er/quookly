"""Finding registry entries, for a client that needs to name one.

Thin, and deliberately still a manager. A route reading the registry directly would be a
client holding a use case, and the first thing that ever wants to change here — ranking
results, restricting them to what a cook has used, resolving against a locale other than
the request's — would have nowhere to go but into the route.
"""

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.contracts.ingredient import (
    IngredientView,
    Origin,
    RegistryEntryView,
    RegistryPageView,
)


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


async def browse(
    cook_id: int,
    *,
    term: str | None = None,
    origin: Origin | None = None,
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
        offset=offset,
        limit=limit,
    )
    return RegistryPageView(
        entries=[
            RegistryEntryView(
                id=entry.id,
                slug=entry.slug,
                name=entry.name,
                kind=entry.kind,
                density=entry.density,
                piece_grams=entry.piece_grams,
                origin=entry.origin,
                allergens=sorted(entry.allergens, key=lambda allergen: allergen.value),
                classified=entry.classified,
            )
            for entry in page.entries
        ],
        total=page.total,
    )
