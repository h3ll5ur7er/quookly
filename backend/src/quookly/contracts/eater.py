"""The people a cook cooks for.

An Eater is not an account (ADR-005). Most people cooked for will never sign in, and
requiring one to record a guest's shellfish allergy would make the feature useless.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quookly.contracts.ingredient import Allergen


class AgeBand(Enum):
    """Drives *suitability* — honey for infants, texture, portion appropriateness.

    Deliberately separate from appetite: two adults of the same age eat different amounts,
    and folding the two together would mean misjudging either portions or safety.
    """

    INFANT = "infant"
    CHILD = "child"
    ADULT = "adult"
    ELDERLY = "elderly"


class Severity(Enum):
    """How seriously a constraint is meant, which is what decides behaviour.

    Without this every constraint is treated alike, and either a disliked ingredient bars a
    menu or a life-threatening allergen appears as a suggestion. Both are wrong.
    """

    MEDICAL = "medical"
    ETHICAL = "ethical"
    INTOLERANCE = "intolerance"
    PREFERENCE = "preference"

    @property
    def excludes(self) -> bool:
        """Whether violating this bars a recipe outright."""
        return self in {Severity.MEDICAL, Severity.ETHICAL}

    @property
    def carries_risk(self) -> bool:
        """Whether not knowing is itself a problem.

        A dislike carries no risk, so an unclassified ingredient raises no doubt about it.
        """
        return self is not Severity.PREFERENCE


@dataclass(frozen=True, slots=True)
class Constraint:
    """One thing an eater avoids, and how seriously.

    Either an allergen class or a specific ingredient — exactly one, because a constraint
    that names both is ambiguous about what it is really avoiding.
    """

    allergen: Allergen | None
    ingredient_slug: str | None
    severity: Severity

    def __post_init__(self) -> None:
        named = [self.allergen is not None, self.ingredient_slug is not None]
        if sum(named) != 1:
            raise ValueError("a constraint names exactly one of an allergen or an ingredient")


#: What one person eats, before anybody is described as eating more or less than it.
STANDARD_PORTION = Decimal("1")


@dataclass(frozen=True, slots=True)
class Eater:
    """Somebody at the table.

    `appetite` multiplies a standard portion. A teenager is 1.4, a small eater 0.6; the
    yield a recipe needs is the sum across everyone attending, not a head count (FR-18).

    A `Decimal` rather than a float, because these are summed and then multiplied through
    every quantity in a recipe: 0.3 + 1.4 + 0.6 has to be 2.3 and not 2.3000000000000003.
    """

    id: int
    cook_id: int
    name: str
    age_band: AgeBand
    appetite: Decimal = STANDARD_PORTION
    constraints: list[Constraint] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.appetite <= 0:
            raise ValueError("an appetite multiplier is greater than zero")


# What crosses the API. These are pydantic rather than dataclasses because they are the
# client boundary: validated on the way in and serialised on the way out.


class ConstraintView(BaseModel):
    """One thing an eater avoids, as a client reads and writes it.

    The same shape in both directions, so an interface can read a household, edit it, and
    send it back without translating between two nearly-identical types.
    """

    model_config = ConfigDict(frozen=True)

    allergen: Allergen | None = None
    ingredient_slug: str | None = Field(default=None, min_length=1, max_length=100)
    severity: Severity

    @model_validator(mode="after")
    def names_exactly_one_thing(self) -> "ConstraintView":
        named = [self.allergen is not None, self.ingredient_slug is not None]
        if sum(named) != 1:
            raise ValueError("a constraint names exactly one of an allergen or an ingredient")
        return self


class EaterView(BaseModel):
    """Somebody at the table, as a client reads them.

    `appetite` is a string for the same reason a quantity's magnitude is: JSON numbers
    are binary floats in a browser, and these are summed to decide how much food to cook.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    age_band: AgeBand
    appetite: str
    constraints: list[ConstraintView]


class EaterInput(BaseModel):
    """An eater being recorded or corrected (UC-6.3, UC-6.4, UC-6.5).

    Carries the whole person, constraints included, because that is what an editing form
    holds. A partial update would need a way to say "and remove this allergy", and the
    version that forgets to is the one that quietly keeps it.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=100)
    age_band: AgeBand
    appetite: Decimal = Field(default=STANDARD_PORTION, gt=0, le=10)
    constraints: list[ConstraintView] = Field(default_factory=list, max_length=50)
