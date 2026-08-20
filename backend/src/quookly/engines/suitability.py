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


def evaluate(ingredients: list[IngredientFacts], eaters: list[Eater]) -> Verdict:
    """Judge a recipe against the people eating it.

    The worst outcome across everyone decides. A known violation outranks a doubt: there
    is nothing left to find out about it.
    """
    findings: list[Finding] = []

    for eater in eaters:
        for constraint in eater.constraints:
            for facts in ingredients:
                if _violates(facts, constraint):
                    findings.append(
                        Finding(
                            eater=eater.name,
                            ingredient=facts.name,
                            severity=constraint.severity,
                            allergen=constraint.allergen,
                            avoidable=facts.optional,
                        )
                    )
                elif not facts.classified and constraint.severity.carries_risk:
                    # Nobody has looked at this ingredient, and this constraint is one
                    # where not knowing matters.
                    findings.append(
                        Finding(
                            eater=eater.name,
                            ingredient=facts.name,
                            severity=constraint.severity,
                            allergen=constraint.allergen,
                            avoidable=facts.optional,
                            unknown=True,
                        )
                    )

    return Verdict(outcome=_outcome(findings), findings=findings)


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
