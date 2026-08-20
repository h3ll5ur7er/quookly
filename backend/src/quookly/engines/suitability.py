"""Whether a set of people can eat a recipe (V5, ADR-006).

A pure function of resolved ingredients and structured constraints. It reads nothing, and
in particular it never reads a claim made in generated text: a model asserting that a
recipe is nut-free carries no weight here, and marzipan is still marzipan.

Two rules decide everything below.

**Structure decides.** A verdict comes from an ingredient's allergen classification, not
from what anybody said about the recipe.

**Unknown is not safe.** An ingredient whose allergens have never been classified makes
the answer *unknown*, never suitable. Silence about a nut is not an absence of nuts.
"""

from dataclasses import dataclass

from quookly.contracts.eater import Constraint, Eater, Severity
from quookly.contracts.ingredient import Allergen
from quookly.contracts.suitability import Finding, Outcome, Verdict


@dataclass(frozen=True, slots=True)
class IngredientFacts:
    """What the engine needs to know about one line of a recipe.

    Passed in rather than fetched. That is what keeps this testable as a table of cases,
    which is the standard a safety-critical component has to meet.
    """

    slug: str
    name: str
    allergens: frozenset[Allergen]
    # Whether anybody has ever classified this ingredient's allergens. False is not the
    # same as an empty set: one means "contains none", the other means "nobody has looked".
    classified: bool
    optional: bool = False


def _violates(facts: IngredientFacts, constraint: Constraint) -> bool:
    """Whether this ingredient is the thing this constraint avoids."""
    if constraint.ingredient_slug is not None:
        return facts.slug == constraint.ingredient_slug
    return constraint.allergen in facts.allergens


# Worst first, which is the order a doubt should be reported at when several apply.
_GRAVITY = (Severity.MEDICAL, Severity.ETHICAL, Severity.INTOLERANCE, Severity.PREFERENCE)


def _worst(constraints: list[Constraint]) -> Severity:
    return next(
        severity
        for severity in _GRAVITY
        if any(constraint.severity is severity for constraint in constraints)
    )


def evaluate(ingredients: list[IngredientFacts], eaters: list[Eater]) -> Verdict:
    """Judge a recipe against the people eating it.

    The worst outcome across everyone decides. A known violation outranks a doubt: there
    is nothing left to find out about it.
    """
    findings: list[Finding] = []

    for eater in eaters:
        for facts in ingredients:
            broken = [
                constraint for constraint in eater.constraints if _violates(facts, constraint)
            ]
            findings.extend(
                Finding(
                    eater=eater.name,
                    ingredient=facts.name,
                    severity=constraint.severity,
                    allergen=constraint.allergen,
                    avoidable=facts.optional,
                )
                for constraint in broken
            )

            # Nobody has looked at this ingredient, so nothing is known about any
            # allergen in it. That is one fact, reported once however many constraints it
            # bears on: a row per constraint fills the verdict with lines that differ in
            # no way a cook can see, and a warning nobody reads is the failure this path
            # exists to avoid. It carries the gravest of those constraints, so collapsing
            # can never make a doubt look milder than it is.
            doubted = [
                constraint
                for constraint in eater.constraints
                if constraint.severity.carries_risk and constraint not in broken
            ]
            if not facts.classified and doubted:
                findings.append(
                    Finding(
                        eater=eater.name,
                        ingredient=facts.name,
                        severity=_worst(doubted),
                        allergen=None,
                        avoidable=facts.optional,
                        unknown=True,
                    )
                )

    return Verdict(outcome=_outcome(findings), findings=_worst_first(findings))


def _worst_first(findings: list[Finding]) -> list[Finding]:
    """Most serious first, so the reason the verdict came out as it did is at the top.

    A long table produces a dozen rows, and the one that decided the answer should not be
    the twelfth. Something the cook can leave out sinks below everything they cannot, and
    a certainty comes before a doubt of the same gravity. The sort is stable, so ties keep
    the recipe's own order and the list does not rearrange itself between visits.
    """
    return sorted(
        findings,
        key=lambda finding: (
            finding.avoidable,
            _GRAVITY.index(finding.severity),
            finding.unknown,
        ),
    )


def _outcome(findings: list[Finding]) -> Outcome:
    """The worst thing found, in order of how much it should stop a cook."""
    if any(
        finding.severity.excludes and not finding.unknown and not finding.avoidable
        for finding in findings
    ):
        return Outcome.UNSUITABLE
    if any(finding.unknown and not finding.avoidable for finding in findings):
        return Outcome.UNKNOWN
    if any(
        finding.severity is Severity.INTOLERANCE and not finding.avoidable for finding in findings
    ):
        return Outcome.CAUTION
    return Outcome.SUITABLE
