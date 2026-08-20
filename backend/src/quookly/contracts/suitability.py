"""What came of asking whether these people can eat this."""

from dataclasses import dataclass, field
from enum import Enum

from quookly.contracts.eater import Severity
from quookly.contracts.ingredient import Allergen


class Outcome(Enum):
    """The answer, worst-first when several apply."""

    UNSUITABLE = "unsuitable"
    UNKNOWN = "unknown"
    CAUTION = "caution"
    SUITABLE = "suitable"


@dataclass(frozen=True, slots=True)
class Finding:
    """Why a verdict came out as it did.

    Always names the eater and the ingredient: a refusal a cook cannot act on is barely
    better than no answer.
    """

    eater: str
    ingredient: str
    severity: Severity
    allergen: Allergen | None = None
    # True when the line is optional, so the recipe works by leaving it out — which is a
    # more useful thing to tell a cook than a refusal.
    avoidable: bool = False
    # True when the ingredient's allergens have never been classified, so this is a doubt
    # rather than a violation.
    unknown: bool = False


@dataclass(frozen=True, slots=True)
class Verdict:
    outcome: Outcome
    findings: list[Finding] = field(default_factory=list)
