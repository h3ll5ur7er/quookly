"""Finding registry entries, for a client that needs to name one.

Thin, and deliberately still a manager. A route reading the registry directly would be a
client holding a use case, and the first thing that ever wants to change here — ranking
results, restricting them to what a cook has used, resolving against a locale other than
the request's — would have nowhere to go but into the route.
"""

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.contracts.ingredient import IngredientView


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
