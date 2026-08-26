"""A cooking session: one meal, being made right now (V15).

The only stateful, device-spanning thing in the system, and the reason execution guidance
earns a manager of its own. A session is server-side (FR-13) because a cook's phone locks,
their tablet sleeps, and a session that dies with the screen is worse than a printed page
(UC-9.7, [ADR-013](../../../doc/07-decisions.md)).

Timers hold **instants**, never remaining seconds. A remaining-seconds timer goes wrong the
moment anything pauses, disconnects, or resumes on another device, and a reduction that
silently loses four minutes is worse than no timer at all.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from quookly.contracts.execution import Attention
from quookly.contracts.matching import MentionView
from quookly.contracts.planning import Sizing
from quookly.contracts.recipe import PresentedLine, QuantityView
from quookly.contracts.suitability import VerdictView


class SessionOutcome(Enum):
    """How a session ended.

    Named for sessions rather than called `Outcome`, because a dietary verdict already has
    that name and one of the two would have to be renamed at the API boundary anyway.

    Two outcomes, not one plus a timeout. The difference is the difference between food
    that was eaten and food that was not, and only one of them is a meal.
    """

    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass(frozen=True, slots=True)
class Timer:
    """One step's timer, as instants rather than as a countdown.

    `running_since` is when it was last started, absent while paused. `elapsed_seconds` is
    what it had already counted before that. The remaining time is arithmetic the client
    does every second; the server does it never, which is what lets two devices agree.
    """

    step_position: int
    running_since: datetime | None
    elapsed_seconds: int

    @property
    def running(self) -> bool:
        return self.running_since is not None


@dataclass(frozen=True, slots=True)
class CookingSession:
    """Where a cook has got to.

    `at_step` is absent while they are still on the mise-en-place, which is where every
    session begins (UC-9.2). Absent is not step zero: "still getting things ready" and
    "doing the first thing" are different places to come back to.
    """

    id: int
    cook_id: int
    plan_slot_id: int
    started_at: datetime
    at_step: int | None = None
    finished_at: datetime | None = None
    outcome: SessionOutcome | None = None
    timers: list[Timer] = field(default_factory=list)

    @property
    def open(self) -> bool:
        return self.outcome is None


# What crosses the API.


class TimerView(BaseModel):
    """A timer as a client reads it, with the duration it is counting towards.

    The duration travels with the timer so a client has one thing to look at rather than
    two: a step whose duration changed under a running timer is a bug, not a feature.
    """

    model_config = ConfigDict(frozen=True)

    step_position: int
    running_since: datetime | None
    elapsed_seconds: int
    duration_seconds: int


class GuidedStepView(BaseModel):
    """One step, with everything needed to do it without looking elsewhere.

    `lines` is the point. A cook at the hob should not have to scroll back to the
    ingredient list to find out how much flour "the flour" was — the quantities the step
    asks for sit with the instruction. Empty where nothing could be matched with
    confidence, which is honest: a step pointing at the wrong ingredient is worse than one
    pointing at none (ADR-040).
    """

    model_config = ConfigDict(frozen=True)

    position: int
    instruction: str
    #: Words in this instruction a cook can look up (UC-9.5). The same marks the recipe
    #: page carries, because looking a word up at the hob must not cost the cook their
    #: place in the recipe.
    mentions: list[MentionView] = []
    duration_seconds: int | None
    temperature_celsius: int | None
    attention: Attention
    lines: list[PresentedLine]
    # Absent until the cook starts one. A timer that exists before it is asked for is a
    # timer already counting down something nobody began.
    timer: TimerView | None


class PrepGroupView(BaseModel):
    """Things to have ready that want the same work doing to them (UC-9.2)."""

    model_config = ConfigDict(frozen=True)

    preparation: str | None
    lines: list[PresentedLine]


class SessionView(BaseModel):
    """A session as the cooking screen reads it: the whole meal, scaled and arranged."""

    model_config = ConfigDict(frozen=True)

    id: int
    plan_slot_id: int
    title: str
    yield_quantity: QuantityView
    serves: str | None
    # How confidently the meal was sized, by the same rule the plan used. A session that
    # could not be scaled to the table is cooking one batch, and the cook has to be able
    # to see that before they start rather than when it runs out.
    sizing: Sizing
    # Whether the people at this meal can eat it. Judged again here on purpose: this is
    # the last moment before the food exists, and a guest may have been added since.
    suitability: VerdictView | None
    mise_en_place: list[PrepGroupView]
    # What had to happen before today. Separate from the method, because a cook standing
    # at the hob cannot act on it and a session that walks them through it first would be
    # walking them through yesterday (ADR-041).
    ahead: list[GuidedStepView]
    steps: list[GuidedStepView]
    at_step: int | None
    started_at: datetime
    finished_at: datetime | None
    outcome: SessionOutcome | None


class StartInput(BaseModel):
    """Which planned meal is being cooked (UC-9.1)."""

    model_config = ConfigDict(frozen=True)

    plan_slot_id: int


class CookNowInput(BaseModel):
    """Which recipe is being cooked outright, with nothing planned (UC-9.1b)."""

    model_config = ConfigDict(frozen=True)

    recipe_id: int


class AtStepInput(BaseModel):
    """Where the cook has got to (UC-9.3)."""

    model_config = ConfigDict(frozen=True)

    # Absent means back to the mise-en-place, which is a real place to be rather than a
    # missing answer.
    position: int | None = None
