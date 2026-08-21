"""What a search or a suggestion came to (V10).

Ranking is a judgement, and a cook is entitled to know which one was made. So a ranked
recipe carries its **reasons** and not merely its position: "you have everything but the
cream" and "uses spinach, which needs eating" are the two facts that make a suggestion worth
following, and a list that only reordered itself would be asking to be trusted rather than
earning it.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from quookly.contracts.recipe import RecipeSummaryView


class Reason(Enum):
    """Why a recipe is where it is in the list."""

    #: Every ingredient it needs is in the pantry.
    HAVE_EVERYTHING = "have_everything"
    #: Most of it is, and the rest is a short list.
    HAVE_MOST = "have_most"
    #: It uses something that is past its date or nearly there.
    USES_SOON = "uses_soon"
    #: Somebody at the table cannot eat it. Ranked down rather than hidden (ADR-010).
    NOT_FOR_EVERYONE = "not_for_everyone"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One recipe as the ranking engine sees it: identity, and facts about it.

    Deliberately not a recipe. Everything the engine needs is a small set of counts, which
    is what lets it be a table of cases with nothing to fetch.
    """

    recipe_id: int
    #: How many of its ingredients the pantry has any of, out of how many it needs.
    have: int
    needs: int
    #: The ingredients it uses that are past their date or close to it.
    pressing: list[str] = field(default_factory=list)
    #: Whether the household can eat it. Absent means nobody has been described, which is
    #: not the same as suitable (ADR-006).
    suitable: bool | None = None
    #: How well it matched the words typed, where any were. Comparable only within one
    #: search, which is why it never leaves the engine.
    relevance: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Ranked:
    recipe_id: int
    reasons: list[Reason]
    #: What it uses that wants eating, named — a count would not tell a cook whether to
    #: bother.
    pressing: list[str]
    #: How many of its ingredients are not in the pantry.
    missing: int


# What leaves the API.


class SuggestionView(BaseModel):
    """A recipe worth cooking, and why it is worth cooking."""

    model_config = ConfigDict(frozen=True)

    recipe: RecipeSummaryView
    reasons: list[Reason]
    pressing: list[str]
    missing: int
