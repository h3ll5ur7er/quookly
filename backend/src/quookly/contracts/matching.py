"""Names that might be the same ingredient, as the matcher reports them.

Everything here is a *suggestion*. Nothing in this module authorises resolving a recipe
line to an ingredient: an import that guessed wrong would attach one food's allergens to
another food's recipe, which is the failure ADR-006 exists to prevent. The matcher ranks;
a person decides.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Resemblance(Enum):
    """Why two names look like the same thing.

    Carried alongside the score for the same reason `RankingEngine` gives reasons
    (ADR-046): a list that only reordered itself would be asking to be trusted rather than
    earning it. "Same words, different order" is something an admin can check at a glance;
    a number on its own is not.
    """

    #: Identical once case and accents are gone — `crème fraîche` and `creme fraiche`.
    SAME_SPELLING = "same_spelling"
    #: The same words in a different order or punctuation — `flour, plain` and `plain flour`.
    SAME_WORDS = "same_words"
    #: Every word of one appears in the other — `flour` and `plain flour`.
    CONTAINS = "contains"
    #: Close enough to be a typo or a variant spelling.
    SPELLING = "spelling"


@dataclass(frozen=True, slots=True)
class Named:
    """A registry entry as the matcher sees it: a slug and everything it answers to.

    Reference data, passed in as an argument. The engine reads no database — that is what
    keeps it a rule engine and its tests a table of cases.
    """

    slug: str
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Resembling:
    """One entry that a written name might mean."""

    slug: str
    #: The spelling that matched, which is not always the entry's canonical name.
    name: str
    confidence: Decimal
    reason: Resemblance


@dataclass(frozen=True, slots=True)
class Duplicate:
    """Two registry entries that might be one ingredient.

    Ordered so `slug` and `other` are stable for a given pair, which keeps the report the
    same from one run to the next.
    """

    slug: str
    other: str
    name: str
    other_name: str
    confidence: Decimal
    reason: Resemblance
