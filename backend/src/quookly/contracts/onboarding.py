"""What a new cook still has to set up, and what they have already settled (V16).

Nothing here records progress. Progress is *derived* from the profile itself (ADR-014),
because a stored completion flag drifts from reality: delete every eater and the flag
still says the household is set up.

One thing the derivation cannot infer, so it is stored: **declared none is not the same as
not answered** (FR-15). A household where genuinely nobody has a dietary restriction looks
exactly like one nobody has been asked about, and telling them apart is the difference
between a setup that finishes and one that nags forever.
"""

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict

#: The languages this instance actually ships catalogues for (FR-10, ADR-025). A locale
#: outside this list would leave a cook with an interface in a language nobody wrote, so it
#: is refused rather than stored.
SUPPORTED_LOCALES = ("en-GB", "de-CH", "fr-CH")


class SetupStep(Enum):
    """The things worth establishing, in the order they are worth asking for.

    Who is eating comes first because it is what the product is about; everything after it
    is a preference about how the answer is shown.
    """

    HOUSEHOLD = "household"
    CONSTRAINTS = "constraints"
    UNITS = "units"
    LOCALE = "locale"


@dataclass(frozen=True, slots=True)
class ProfileState:
    """What a cook's profile currently holds, reduced to what setup depends on.

    Counts rather than the records themselves: the engine decides whether a question has
    been answered, not what the answer was.
    """

    eaters: int
    eaters_with_constraints: int
    chosen_units: int
    locale_chosen: bool
    declared: frozenset[SetupStep]


@dataclass(frozen=True, slots=True)
class StepStatus:
    """One step, and whether it is settled.

    `declared` separates "you told us nobody has any" from "somebody does" — both are
    done, and they are not the same thing to show a cook.
    """

    step: SetupStep
    done: bool
    declared: bool


@dataclass(frozen=True, slots=True)
class SetupProgress:
    """Everything a setup screen needs, derived fresh every time it is asked for."""

    steps: list[StepStatus]
    next_step: SetupStep | None
    complete: bool


# What crosses the API.


class StepStatusView(BaseModel):
    model_config = ConfigDict(frozen=True)

    step: SetupStep
    done: bool
    declared: bool


class SetupProgressView(BaseModel):
    """What is still missing from the setup, and what to do next (UC-10.3)."""

    model_config = ConfigDict(frozen=True)

    steps: list[StepStatusView]
    next_step: SetupStep | None
    complete: bool
