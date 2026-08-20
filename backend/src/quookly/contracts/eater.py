"""The people a cook cooks for.

An Eater is not an account (ADR-005). Most people cooked for will never sign in, and
requiring one to record a guest's shellfish allergy would make the feature useless.
"""

from dataclasses import dataclass, field
from enum import Enum

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


@dataclass(frozen=True, slots=True)
class Eater:
    """Somebody at the table.

    `appetite` multiplies a standard portion. A teenager is 1.4, a small eater 0.6; the
    yield a recipe needs is the sum across everyone attending, not a head count (FR-18).
    """

    id: int
    name: str
    age_band: AgeBand
    appetite: float
    constraints: list[Constraint] = field(default_factory=list)
