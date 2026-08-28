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
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from quookly.contracts.ingredient import Allergen, IngredientKind, Origin


class PageKind(Enum):
    """Which section of the Academy a page belongs to.

    The field exists so that the second section was not a migration (ADR-057), which is
    what it turned out to be worth.
    """

    TECHNIQUE = "technique"
    #: About a food rather than about doing something. Names a registry entry, and shows
    #: that entry's facts by reading them rather than by holding a copy (ADR-061).
    INGREDIENT = "ingredient"


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
class Entry:
    """The registry's facts about the food a page is about, as read at the time.

    Read rather than stored (ADR-061). No copy means no copy to go stale, and correcting
    the registry corrects every page about it.

    `classified` travels with `allergens` and is the reason this is not just a list: an
    empty list with `classified` false means *nobody has looked*, and a page that renders
    that as "allergens: none" is the ADR-006 failure with better typography.
    """

    slug: str
    name: str
    kind: IngredientKind
    allergens: list[Allergen]
    classified: bool
    density: Decimal | None
    piece_grams: Decimal | None
    has_nutrition: bool


@dataclass(frozen=True, slots=True)
class Listing:
    """A page as it appears in a list of pages.

    Not a `Claimant`, which means *a page that answers to some term* — every claimant is
    approved by definition (ADR-060), so a claimant carrying a review state would be a
    field that is always true. Browsing is the other question, and it is the one where an
    author needs to see that nobody has read their page yet.
    """

    slug: str
    name: str
    summary: str
    approved: bool
    kind: PageKind
    #: The food this page is about, for a page in the ingredient section. Carried so the
    #: manager can ask the registry where that food sits without re-reading every page —
    #: the Academy does not store the answer, because where a carrot sits is a fact about
    #: the carrot (ADR-061, ADR-067).
    ingredient_id: int | None = None


@dataclass(frozen=True, slots=True)
class Reader:
    """Who is reading the Academy: somebody here, or a stranger.

    The difference decides two things. **Which language** — a cook has chosen one and a
    stranger has to say. And **how much** — a stranger sees only what somebody here has
    read, because publishing a page is a different act from letting the people here see a
    draft (ADR-063).

    A value rather than two parameters threaded through three functions: the pair is one
    fact, and separating them is how one call site comes to pass a locale and forget the
    visibility.
    """

    cook_id: int | None = None
    #: What a stranger asked to read in. Ignored where there is a cook, who has chosen.
    locale: str | None = None

    @property
    def is_a_stranger(self) -> bool:
        return self.cook_id is None


@dataclass(frozen=True, slots=True)
class Standing:
    """Where a page stands, for deciding who may do what to it.

    Separate from `Page`, which is a page as a *reader* reads it: this answers questions
    about the page rather than reporting what it says, and it answers them for a page that
    has been put away — which a reader cannot see at all (ADR-060).
    """

    approved: bool
    #: Who wrote it, where anybody here did. Absent for a page this instance shipped with.
    written_by: int | None
    archived: bool


@dataclass(frozen=True, slots=True)
class Claimant:
    """A page that answers to some term, and what it is about."""

    slug: str
    name: str
    summary: str


@dataclass(frozen=True, slots=True)
class Picture:
    """A photograph on a page, and what it shows."""

    id: int
    media_id: str
    description: str
    locale: str


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
    #: What it looks like. A page about julienne without a photograph of julienne is a
    #: knife cut explained in words (ADR-057).
    pictures: list[Picture] = field(default_factory=list)
    #: The food this page is about, for a page in the ingredient section. Read from the
    #: registry each time rather than stored, so there is no copy to disagree (ADR-061).
    entry: Entry | None = None


class EntryView(BaseModel):
    """The registry's facts about a food, as an ingredient page shows them."""

    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    kind: IngredientKind
    allergens: list[Allergen]
    #: Whether anybody has looked. An empty `allergens` with this false means "unknown",
    #: not "contains none" (ADR-006).
    classified: bool
    density: Decimal | None
    piece_grams: Decimal | None
    has_nutrition: bool


class ClaimantView(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    summary: str


class PictureView(BaseModel):
    """A picture as a client reads it."""

    model_config = ConfigDict(frozen=True)

    id: int
    #: Where to fetch the bytes. A client builds `/api/v1/media/{media_id}` from this.
    media_id: str
    #: Alt text. Not optional: a picture without it is an accessibility failure, and the
    #: rule here is that accessibility is checked as UI is built rather than retrofitted.
    description: str
    #: The language the description is written in, which is not always the reader's.
    locale: str


class PageSummaryView(BaseModel):
    """Enough to list a page without its explanation."""

    model_config = ConfigDict(frozen=True)

    slug: str
    kind: PageKind
    name: str
    summary: str
    #: Whether anybody here has read it. An unreviewed page is listed and readable; what it
    #: does not do is get matched into anybody's recipe (ADR-060).
    approved: bool = True
    #: Where the food this page is about sits, as a slug into the registry's tree. Absent
    #: for a technique, which is not a food and has no aisle — and for a food nobody has
    #: placed. It is what lets the Academy be read as *Ingredients > Vegetables > Carrot*
    #: rather than as one flat alphabet (ADR-067).
    category_slug: str | None = None


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
    #: Whether the reader of this response may rewrite its wording.
    #:
    #: Answered by the server rather than derived by a screen: the rule has three parts
    #: (administrator, author, not yet approved) and a client that re-derives it will get
    #: one of them slightly wrong and offer a button that 403s (ADR-060).
    may_rewrite: bool = False
    #: What the registry knows about the food this page is about, where it is about one.
    #: Read, never stored: a paragraph and a column that both state an allergen will one
    #: day disagree, and the reader believes the paragraph (ADR-006, ADR-061).
    entry: EntryView | None = None
    caution: str | None = None
    also: list[ClaimantView] = []
    pictures: list[PictureView] = []
