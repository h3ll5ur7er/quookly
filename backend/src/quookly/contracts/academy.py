"""The Academy, as it travels between layers.

A page explains one thing a cook might not know. It carries a **kind** rather than being a
technique, because the volatility was never "techniques" — `curdle` is not something you
do and `al dente` is a doneness, and the ingredient registry owes a page of its own
(ADR-057).

Nothing here is ever read by anything that computes. `SuitabilityEngine` and
`NutritionEngine` do not see it, and a layer contract says so (ADR-056): as long as an
explanation is only shown to a person, a wrong one is a bad paragraph rather than a wrong
verdict.
"""

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict

from quookly.contracts.ingredient import Origin


class PageKind(Enum):
    """Which section of the Academy a page belongs to.

    One value today and the reason the field exists: naming the entity after the first
    section anybody wrote would have made the second one a migration (ADR-057).
    """

    TECHNIQUE = "technique"


@dataclass(frozen=True, slots=True)
class Wording:
    """A page as one language writes it.

    `spellings` is the load-bearing field. It is what a recipe step's own words are matched
    against (ADR-055), so a bare word that means something else in a recipe does not belong
    in it — putting the variation here rather than in a similarity score is what lets a
    person see and correct it.
    """

    name: str
    spellings: list[str]
    summary: str
    explanation: str
    caution: str | None = None
    #: Whether the name on its own reliably means this page.
    #:
    #: Usually it does — `blanch` in a recipe is blanching. Sometimes the word has another
    #: life: German `sieben` is both *to sift* and *the number seven*, so "sieben Minuten"
    #: would link to sifting; English `rest` is also *the rest of the flour*, and `reduce`
    #: is also *reduce the heat*. Those pages keep their name and are found by their
    #: spellings instead. A fact about the language, written down where somebody can see
    #: and correct it — which is the whole of ADR-055.
    name_matches: bool = True


@dataclass(frozen=True, slots=True)
class NewPage:
    """A page to add, in every language it is written in."""

    slug: str
    kind: PageKind
    wordings: dict[str, Wording]


@dataclass(frozen=True, slots=True)
class Claimant:
    """A page that answers to some term, and what it is about."""

    slug: str
    name: str
    summary: str


@dataclass(frozen=True, slots=True)
class Page:
    """A page as one reader reads it."""

    slug: str
    kind: PageKind
    name: str
    summary: str
    explanation: str
    spellings: list[str]
    origin: Origin
    #: Whether a model wrote it, and separately whether anybody has checked it. Two fields
    #: because they are two questions, the same argument ADR-051 made for the registry.
    generated: bool
    approved: bool
    caution: str | None = None
    #: Other pages this one's name also belongs to. Shown at the top the way an
    #: encyclopedia does, because several pages may claim a term here (ADR-058).
    also: list[Claimant] = field(default_factory=list)


class ClaimantView(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    summary: str


class PageSummaryView(BaseModel):
    """Enough to list a page without its explanation."""

    model_config = ConfigDict(frozen=True)

    slug: str
    kind: PageKind
    name: str
    summary: str


class PageView(BaseModel):
    """A page as a client reads it."""

    model_config = ConfigDict(frozen=True)

    slug: str
    kind: PageKind
    name: str
    summary: str
    explanation: str
    spellings: list[str]
    origin: Origin
    generated: bool
    approved: bool
    caution: str | None = None
    also: list[ClaimantView] = []
