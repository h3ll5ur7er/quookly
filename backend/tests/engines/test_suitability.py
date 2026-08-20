"""Can these people eat this? (V5, ADR-006)

The most consequential rule engine in the system, and the reason it is a pure function:
this file is a table of cases with no fixtures, no database and no model — which is what a
safety-critical component needs in order to be argued about.

Two rules run through every case below.

**Structure decides, never prose.** A verdict comes from resolved ingredients and their
allergen classification. Nothing here reads a claim made in generated text.

**Unknown is not safe.** An ingredient whose allergens have never been classified makes a
recipe *unknown*, not suitable. Silence about a nut is not an absence of nuts.
"""

import pytest

from quookly.contracts.eater import AgeBand, Constraint, Eater, Severity
from quookly.contracts.ingredient import Allergen
from quookly.contracts.suitability import Outcome
from quookly.engines import suitability
from quookly.engines.suitability import IngredientFacts


def facts(
    name: str,
    *allergens: Allergen,
    classified: bool = True,
    optional: bool = False,
) -> IngredientFacts:
    return IngredientFacts(
        slug=name.replace(" ", "-"),
        name=name,
        allergens=frozenset(allergens),
        classified=classified,
        optional=optional,
    )


def eater(name: str, *constraints: Constraint) -> Eater:
    return Eater(
        id=1,
        cook_id=1,
        name=name,
        age_band=AgeBand.ADULT,
        constraints=list(constraints),
    )


def avoids(allergen: Allergen, severity: Severity) -> Constraint:
    return Constraint(allergen=allergen, ingredient_slug=None, severity=severity)


def dislikes(slug: str, severity: Severity = Severity.PREFERENCE) -> Constraint:
    return Constraint(allergen=None, ingredient_slug=slug, severity=severity)


BUTTER = facts("unsalted butter", Allergen.MILK)
FLOUR = facts("plain flour", Allergen.GLUTEN)
SUGAR = facts("caster sugar")


class TestNobodyToOffend:
    def test_a_recipe_with_no_eaters_is_suitable(self) -> None:
        assert suitability.evaluate([BUTTER, FLOUR], []).outcome is Outcome.SUITABLE

    def test_an_eater_with_no_constraints_can_eat_anything_classified(self) -> None:
        verdict = suitability.evaluate([BUTTER, FLOUR], [eater("Emanuel")])
        assert verdict.outcome is Outcome.SUITABLE
        assert verdict.findings == []


class TestHardExclusions:
    def test_a_medical_allergy_makes_a_recipe_unsuitable(self) -> None:
        sofia = eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL))
        assert suitability.evaluate([BUTTER, FLOUR], [sofia]).outcome is Outcome.UNSUITABLE

    def test_an_ethical_constraint_makes_a_recipe_unsuitable(self) -> None:
        vegan = eater("Ruth", avoids(Allergen.MILK, Severity.ETHICAL))
        assert suitability.evaluate([BUTTER], [vegan]).outcome is Outcome.UNSUITABLE

    def test_the_verdict_names_the_ingredient_responsible(self) -> None:
        """A refusal a cook cannot act on is barely better than none."""
        sofia = eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL))
        finding = suitability.evaluate([BUTTER, FLOUR], [sofia]).findings[0]
        assert finding.ingredient == "unsalted butter"
        assert finding.eater == "Sofia"
        assert finding.allergen is Allergen.MILK
        assert finding.severity is Severity.MEDICAL

    def test_an_ingredient_someone_avoids_by_name_is_caught(self) -> None:
        """Not everything anyone avoids is one of the fourteen."""
        no_mushrooms = eater("Emanuel", dislikes("shiitake", Severity.MEDICAL))
        verdict = suitability.evaluate([facts("shiitake"), SUGAR], [no_mushrooms])
        assert verdict.outcome is Outcome.UNSUITABLE
        assert verdict.findings[0].ingredient == "shiitake"


class TestSofterConstraints:
    def test_an_intolerance_warns_rather_than_refuses(self) -> None:
        """Discomfort is a decision for the cook, not a bar."""
        verdict = suitability.evaluate(
            [BUTTER], [eater("Jonas", avoids(Allergen.MILK, Severity.INTOLERANCE))]
        )
        assert verdict.outcome is Outcome.CAUTION
        assert verdict.findings[0].severity is Severity.INTOLERANCE

    def test_a_dislike_is_noted_and_nothing_more(self) -> None:
        """Rank it down, do not exclude it. A disliked ingredient is still edible."""
        verdict = suitability.evaluate([facts("olives")], [eater("Mila", dislikes("olives"))])
        assert verdict.outcome is Outcome.SUITABLE
        assert verdict.findings[0].severity is Severity.PREFERENCE

    def test_a_hard_exclusion_outranks_a_dislike(self) -> None:
        table = [
            eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL)),
            eater("Mila", dislikes("caster sugar")),
        ]
        assert suitability.evaluate([BUTTER, SUGAR], table).outcome is Outcome.UNSUITABLE


class TestWhatIsNotKnown:
    def test_an_unclassified_ingredient_makes_the_answer_unknown(self) -> None:
        """Silence about a nut is not an absence of nuts (ADR-006)."""
        mystery = facts("grandmother's spice mix", classified=False)
        verdict = suitability.evaluate(
            [mystery], [eater("Sofia", avoids(Allergen.PEANUTS, Severity.MEDICAL))]
        )
        assert verdict.outcome is Outcome.UNKNOWN

    def test_unknown_is_reported_with_the_ingredient_that_caused_it(self) -> None:
        mystery = facts("grandmother's spice mix", classified=False)
        verdict = suitability.evaluate(
            [mystery], [eater("Sofia", avoids(Allergen.PEANUTS, Severity.MEDICAL))]
        )
        assert verdict.findings[0].ingredient == "grandmother's spice mix"

    def test_something_definitely_wrong_outranks_something_merely_unknown(self) -> None:
        """A known violation is decisive; there is nothing left to find out."""
        mystery = facts("grandmother's spice mix", classified=False)
        sofia = eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL))
        assert suitability.evaluate([BUTTER, mystery], [sofia]).outcome is Outcome.UNSUITABLE

    def test_an_unclassified_ingredient_is_ignored_when_nobody_is_at_risk(self) -> None:
        """Unknown only matters against a constraint that could be violated."""
        mystery = facts("grandmother's spice mix", classified=False)
        assert suitability.evaluate([mystery], [eater("Emanuel")]).outcome is Outcome.SUITABLE

    def test_a_dislike_does_not_turn_an_unclassified_ingredient_into_a_doubt(self) -> None:
        """Preferences carry no risk, so nothing about them is unsafe to not know."""
        mystery = facts("grandmother's spice mix", classified=False)
        verdict = suitability.evaluate([mystery], [eater("Mila", dislikes("olives"))])
        assert verdict.outcome is Outcome.SUITABLE


class TestOptionalIngredients:
    def test_an_optional_ingredient_does_not_bar_a_recipe(self) -> None:
        """It can simply be left out, which is more useful than a refusal."""
        butter = facts("unsalted butter", Allergen.MILK, optional=True)
        verdict = suitability.evaluate(
            [FLOUR, butter], [eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL))]
        )
        assert verdict.outcome is Outcome.SUITABLE

    def test_but_it_is_still_reported_so_the_cook_knows_to_omit_it(self) -> None:
        butter = facts("unsalted butter", Allergen.MILK, optional=True)
        finding = suitability.evaluate(
            [butter], [eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL))]
        ).findings[0]
        assert finding.avoidable is True
        assert finding.ingredient == "unsalted butter"

    def test_an_optional_unclassified_ingredient_does_not_cast_doubt(self) -> None:
        """It can be left out, so there is nothing left to be unsure about."""
        mystery = facts("grandmother's spice mix", classified=False, optional=True)
        verdict = suitability.evaluate(
            [FLOUR, mystery], [eater("Sofia", avoids(Allergen.PEANUTS, Severity.MEDICAL))]
        )
        assert verdict.outcome is Outcome.SUITABLE
        assert verdict.findings[0].avoidable is True
        assert verdict.findings[0].unknown is True

    def test_a_required_ingredient_is_not_avoidable(self) -> None:
        finding = suitability.evaluate(
            [BUTTER], [eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL))]
        ).findings[0]
        assert finding.avoidable is False


class TestSeveralEaters:
    def test_every_eater_is_checked(self) -> None:
        table = [
            eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL)),
            eater("Jonas", avoids(Allergen.GLUTEN, Severity.INTOLERANCE)),
        ]
        findings = suitability.evaluate([BUTTER, FLOUR], table).findings
        assert {finding.eater for finding in findings} == {"Sofia", "Jonas"}

    def test_the_worst_outcome_decides(self) -> None:
        table = [
            eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL)),
            eater("Jonas", avoids(Allergen.GLUTEN, Severity.INTOLERANCE)),
        ]
        assert suitability.evaluate([BUTTER, FLOUR], table).outcome is Outcome.UNSUITABLE

    def test_one_persons_constraint_does_not_become_everyones(self) -> None:
        table = [eater("Sofia", avoids(Allergen.MILK, Severity.MEDICAL)), eater("Emanuel")]
        findings = suitability.evaluate([BUTTER], table).findings
        assert [finding.eater for finding in findings] == ["Sofia"]


class TestTheShapeOfAConstraint:
    def test_a_constraint_names_exactly_one_thing(self) -> None:
        with pytest.raises(ValueError):
            Constraint(allergen=Allergen.MILK, ingredient_slug="butter", severity=Severity.MEDICAL)

    def test_a_constraint_must_name_something(self) -> None:
        with pytest.raises(ValueError):
            Constraint(allergen=None, ingredient_slug=None, severity=Severity.MEDICAL)


class TestTheEngineItself:
    def test_it_reads_nothing_but_its_arguments(self) -> None:
        """The property that makes this file a table of cases, and ADR-006 enforceable."""
        import inspect

        source = inspect.getsource(suitability)
        for forbidden in ("access", "session", "await", "requests", "httpx"):
            assert forbidden not in source, f"{forbidden!r} has no business in a rule engine"


class TestDoubtIsReportedOnce:
    """An unclassified ingredient is one fact, however many constraints it bears on.

    Nobody has looked at it, so nothing is known about *any* allergen in it. Reporting
    that once per constraint fills the verdict with rows that differ in no way a cook can
    see — and a warning nobody reads is the failure mode this whole path exists to avoid.
    """

    def test_one_row_per_ingredient_not_per_constraint(self) -> None:
        mira = eater(
            "Mira",
            avoids(Allergen.PEANUTS, Severity.MEDICAL),
            avoids(Allergen.MILK, Severity.INTOLERANCE),
            avoids(Allergen.GLUTEN, Severity.MEDICAL),
        )
        verdict = suitability.evaluate([facts("mystery paste", classified=False)], [mira])
        assert len(verdict.findings) == 1

    def test_it_is_still_unknown(self) -> None:
        mira = eater(
            "Mira",
            avoids(Allergen.PEANUTS, Severity.MEDICAL),
            avoids(Allergen.MILK, Severity.INTOLERANCE),
        )
        verdict = suitability.evaluate([facts("mystery paste", classified=False)], [mira])
        assert verdict.outcome is Outcome.UNKNOWN
        assert verdict.findings[0].unknown is True

    def test_the_row_carries_the_most_serious_reason_to_worry(self) -> None:
        """Collapsing must not soften it: an unchecked ingredient under a medical
        constraint is a more serious doubt than the same one under an intolerance."""
        mira = eater(
            "Mira",
            avoids(Allergen.MILK, Severity.INTOLERANCE),
            avoids(Allergen.PEANUTS, Severity.MEDICAL),
        )
        verdict = suitability.evaluate([facts("mystery paste", classified=False)], [mira])
        assert verdict.findings[0].severity is Severity.MEDICAL

    def test_each_eater_still_gets_their_own_row(self) -> None:
        verdict = suitability.evaluate(
            [facts("mystery paste", classified=False)],
            [
                eater("Mira", avoids(Allergen.PEANUTS, Severity.MEDICAL)),
                eater("Jonas", avoids(Allergen.MILK, Severity.INTOLERANCE)),
            ],
        )
        assert {finding.eater for finding in verdict.findings} == {"Mira", "Jonas"}

    def test_each_unchecked_ingredient_still_gets_its_own_row(self) -> None:
        mira = eater("Mira", avoids(Allergen.PEANUTS, Severity.MEDICAL))
        verdict = suitability.evaluate(
            [facts("mystery paste", classified=False), facts("odd jam", classified=False)],
            [mira],
        )
        assert {finding.ingredient for finding in verdict.findings} == {"mystery paste", "odd jam"}

    def test_a_known_violation_is_still_reported_alongside_the_doubt(self) -> None:
        """Different facts: one constraint is definitely broken, the others are unknown."""
        mira = eater(
            "Mira",
            dislikes("odd-jam", Severity.MEDICAL),
            avoids(Allergen.PEANUTS, Severity.MEDICAL),
        )
        verdict = suitability.evaluate([facts("odd jam", classified=False)], [mira])
        assert [finding.unknown for finding in verdict.findings] == [False, True]
        assert verdict.outcome is Outcome.UNSUITABLE


class TestOrder:
    """The most serious reason is reported first.

    With four eaters and a long ingredient list a verdict runs to a dozen rows, and the
    one that decided it should not be the twelfth. Ties keep the recipe's own order, so
    the list stays predictable between visits.
    """

    def test_the_blocker_comes_before_the_caution(self) -> None:
        mira = eater(
            "Mira",
            avoids(Allergen.MILK, Severity.INTOLERANCE),
            avoids(Allergen.GLUTEN, Severity.MEDICAL),
        )
        verdict = suitability.evaluate(
            [facts("butter", Allergen.MILK), facts("flour", Allergen.GLUTEN)], [mira]
        )
        assert [finding.ingredient for finding in verdict.findings] == ["flour", "butter"]

    def test_a_certainty_comes_before_a_doubt_of_the_same_gravity(self) -> None:
        mira = eater(
            "Mira",
            dislikes("odd-jam", Severity.MEDICAL),
            avoids(Allergen.PEANUTS, Severity.MEDICAL),
        )
        verdict = suitability.evaluate([facts("odd jam", classified=False)], [mira])
        assert [finding.unknown for finding in verdict.findings] == [False, True]

    def test_something_avoidable_sinks_below_something_that_is_not(self) -> None:
        """A line the cook can simply leave out is the least urgent thing on the list."""
        mira = eater(
            "Mira",
            avoids(Allergen.PEANUTS, Severity.MEDICAL),
            avoids(Allergen.MILK, Severity.INTOLERANCE),
        )
        verdict = suitability.evaluate(
            [facts("peanuts", Allergen.PEANUTS, optional=True), facts("butter", Allergen.MILK)],
            [mira],
        )
        assert [finding.ingredient for finding in verdict.findings] == ["butter", "peanuts"]

    def test_ties_keep_the_order_the_recipe_is_written_in(self) -> None:
        mira = eater("Mira", avoids(Allergen.MILK, Severity.INTOLERANCE))
        verdict = suitability.evaluate(
            [facts("butter", Allergen.MILK), facts("cream", Allergen.MILK)], [mira]
        )
        assert [finding.ingredient for finding in verdict.findings] == ["butter", "cream"]
