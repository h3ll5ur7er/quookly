"""What a page turns out to hold, once the furniture is taken away."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ReadableContent:
    """A fetched page, reduced to what is worth reading.

    Both halves are returned without either being preferred. `text` is the prose with
    navigation, comments and newsletter pleading removed; `structured` is whatever
    schema.org metadata the page embedded, exactly as it was found. Deciding which to
    believe is interpretation (V2) and does not belong to the layer that does the
    fetching.
    """

    #: Where the content actually came from, after any redirects. Recipes record their
    #: provenance (V1), and the URL that was pasted may not be the one that answered.
    url: str
    text: str
    title: str | None = None
    structured: list[dict[str, Any]] = field(default_factory=list)
