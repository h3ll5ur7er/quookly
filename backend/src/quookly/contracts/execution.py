"""Execution: what a recipe asks of the cook, and how long for (V15).

Separate from the recipe itself, which is what is *written*. These are things derived from
it — nothing here is stored, and nothing here can disagree with the steps it came from.
"""

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Attention(Enum):
    """How much of the cook this step asks for (V15, ADR-037).

    The field that turns a pile of durations into the two numbers anybody actually wants:
    how long you are working, and how long until you eat. A cake is twenty minutes of work
    and ninety of waiting, and one figure covering both describes neither.

    `AHEAD` is the case that is not a third number. Soaking beans overnight is eight hours
    in which the cook is asleep: adding it to a total makes a weeknight dish read as an
    ordeal, and dropping it silently lets somebody start dinner at six and discover the
    beans wanted starting yesterday.
    """

    #: Chopping, stirring, shaping. Counts towards hands-on and towards total.
    HANDS_ON = "hands_on"
    #: Baking, simmering, resting — the cook is around but not working. Total only.
    WAITING = "waiting"
    #: Proving overnight, marinating, chilling. Neither; surfaced as a lead time.
    AHEAD = "ahead"


@dataclass(frozen=True, slots=True)
class Span:
    """A stretch of time, and whether it is the whole of it.

    `at_least` is not a detail. A recipe where one step forgot to say how long it takes
    still has a floor, and the floor is worth reporting — but reporting it as if it were
    the answer is how somebody ends up eating at ten. Same rule as an unclassified
    allergen and an unreadable yield: absence does not get to read as a value.
    """

    seconds: int
    at_least: bool


@dataclass(frozen=True, slots=True)
class Timing:
    """How long a recipe takes, in the numbers a cook actually asks for.

    Any of the three may be absent, and absent means *nobody said* rather than *none*. A
    cake whose steps carry no durations reports nothing at all, because "at least 0 min"
    reads as a fact and is not one.
    """

    #: How long the cook has to be doing something. *Can I do this tonight?*
    hands_on: Span | None
    #: How long from starting to eating. *When do we eat?*
    total: Span | None
    #: Work that happens without the cook — soaking, proving, chilling. Absent unless the
    #: recipe has some. Surfaced as a lead rather than folded into the total, because
    #: eight hours of sleeping beans is not eight hours of cooking.
    ahead: Span | None


@dataclass(frozen=True, slots=True)
class PrepGroup:
    """Ingredient lines that want the same work doing to them before anything starts.

    `lines` are **positions in the recipe's own line list**, not content. That is what
    keeps execution guidance out of the measurement business: an engine that returns
    indices cannot scale, convert or round anything, so V4 stays in one place by
    construction rather than by a rule somebody has to remember (see `plan`).
    """

    #: The work — "finely chopped", "softened". Absent for the group that wants nothing
    #: doing to it, which is the one a cook simply weighs out.
    preparation: str | None
    lines: list[int]


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """One step, with the ingredient lines it names.

    `lines` is what makes a step readable at the hob without scrolling back: the cook sees
    "225 g plain flour" beside the instruction that asks for it. Empty where nothing could
    be matched with confidence, which is the honest answer — a step pointing at the wrong
    ingredient is worse than one pointing at none.
    """

    position: int
    lines: list[int]


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """A recipe arranged for doing rather than for reading (V15)."""

    #: Everything to have ready, grouped by the work it wants.
    mise_en_place: list[PrepGroup]
    #: What has to happen before the cook can start at all — soaking, proving overnight.
    #: The leading run only; see `plan`.
    ahead: list[PlannedStep]
    #: The method, in order, with the lead already taken off the front.
    steps: list[PlannedStep]


# What leaves the API.


class SpanView(BaseModel):
    """A stretch of time as a client reads it.

    Seconds rather than a rendered string: "1 h 50" is four words in three languages, and
    the client already knows which one it is speaking. `at_least` is carried separately for
    the same reason — a screen decides whether that reads as a prefix, a tilde or a mark.
    """

    model_config = ConfigDict(frozen=True)

    seconds: int
    at_least: bool


class TimingView(BaseModel):
    model_config = ConfigDict(frozen=True)

    hands_on: SpanView | None = None
    total: SpanView | None = None
    ahead: SpanView | None = None

    @classmethod
    def of(cls, timing: Timing | None) -> "TimingView | None":
        """The engine's answer as a client reads it, absence and all."""
        if timing is None:
            return None
        return cls(
            hands_on=_span(timing.hands_on),
            total=_span(timing.total),
            ahead=_span(timing.ahead),
        )


def _span(span: Span | None) -> SpanView | None:
    return None if span is None else SpanView(seconds=span.seconds, at_least=span.at_least)
