"""What reading a page produced (V2).

Interpretation deals in *names*, not registry ids. Resolving "plain flour" to a registry
entry happens against the registry, never against what a model said — an unresolvable
ingredient is reported (FR-9), never invented. That resolution belongs to the manager, so
nothing here has an ingredient id in it.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from quookly.contracts.execution import Attention
from quookly.contracts.measure import Unit


class Source(Enum):
    """Where a reading came from, which is worth keeping.

    A recipe that came out wrong is a different investigation depending on whether the
    page lied in its metadata or a model misread its prose.
    """

    METADATA = "metadata"
    MODEL = "model"


@dataclass(frozen=True, slots=True)
class InterpretedLine:
    """One ingredient line, as read.

    `magnitude` and `unit` are absent together for a line that carries no quantity, and
    for one whose quantity could not be read. Those are different situations and the
    second is worth showing a cook, which is what `written` is for: the line exactly as
    the page had it, so a reading can be checked against its source.
    """

    ingredient: str
    magnitude: Decimal | None = None
    unit: Unit | None = None
    preparation: str | None = None
    optional: bool = False
    written: str = ""


@dataclass(frozen=True, slots=True)
class InterpretedStep:
    instruction: str
    duration_seconds: int | None = None
    temperature_celsius: int | None = None
    #: How much of the cook this step asks for. Hands-on unless the page gave a reason to
    #: think otherwise — a `cookTime` says the last step is waiting, and a model reading
    #: prose can say so for the rest.
    attention: Attention = Attention.HANDS_ON


@dataclass(frozen=True, slots=True)
class InterpretedRecipe:
    """A recipe as read from a page, before anything is resolved or stored."""

    title: str
    source: Source
    summary: str | None = None
    yield_magnitude: Decimal | None = None
    yield_unit: Unit | None = None
    # How many people the page says it feeds, where its yield says something else —
    # "makes 12 pancakes (serves 4)". Absent is the common case and a real answer:
    # nothing here invents a pieces-per-serving figure.
    serves: Decimal | None = None
    lines: list[InterpretedLine] = field(default_factory=list)
    steps: list[InterpretedStep] = field(default_factory=list)
    #: What language the prose is in, as a bare code — `de`, not `de-CH`. Read from the
    #: page rather than assumed, and **absent where the page did not say**: a recipe whose
    #: language nobody knows is one nothing can translate *from*, which is a better answer
    #: than translating out of the wrong language (ADR-032).
    language: str | None = None
