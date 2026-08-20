"""Finding registry entries, for a client that needs to name one.

Thin, and deliberately still a manager. A route reading the registry directly would be a
client holding a use case, and the first thing that ever wants to change here — ranking
results, restricting them to what a cook has used, resolving against a locale other than
the request's — would have nowhere to go but into the route.
"""

from quookly.access import ingredient as registry
from quookly.contracts.ingredient import IngredientView


async def search(term: str, locale: str) -> list[IngredientView]:
    """Registry entries whose name matches `term`, for the caller to pick from."""
    found = await registry.search(term, locale)
    return [
        IngredientView(id=entry.id, slug=entry.slug, name=entry.name, kind=entry.kind)
        for entry in found
    ]
