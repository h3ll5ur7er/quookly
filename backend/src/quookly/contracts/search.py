"""What searching produced (V10).

Deliberately thin. A hit is an identity and how well it matched — nothing about the recipe
itself, because the index holds a copy of some of a recipe's words and is never the place to
read a recipe from.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Hit:
    """One recipe the index matched, and how strongly.

    `score` is comparable within one query and meaningless between two: BM25 depends on the
    collection, so a 3.1 today and a 3.1 tomorrow are not the same claim. It exists to order
    a list, never to be shown to anybody.
    """

    recipe_id: int
    score: Decimal
