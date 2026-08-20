"""What came of asking whether these people can eat this."""

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict

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


# What crosses the API.


class FindingView(BaseModel):
    """One reason behind a verdict, as a client reads it."""

    model_config = ConfigDict(frozen=True)

    eater: str
    ingredient: str
    severity: Severity
    allergen: Allergen | None = None
    avoidable: bool = False
    unknown: bool = False


class VerdictView(BaseModel):
    """Whether the household can eat this, and why.

    Absent rather than `suitable` when there is nobody to judge against: a reassurance
    about a question nobody asked is worse than silence, and a cook who has not yet
    described their household should be told nothing rather than told yes.
    """

    model_config = ConfigDict(frozen=True)

    outcome: Outcome
    findings: list[FindingView]
