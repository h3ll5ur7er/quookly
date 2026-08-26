"""Which written names might mean the same ingredient.

A rule engine, so these are a table of cases with no fixtures, no database and no mocks.

Several of them are regressions against a first version that was measured on the shipped
registry of nine hundred generic foods and found to be worse than useless: its highest
scoring "duplicate" was `condensed milk, sweetened` against `condensed milk, unsweetened`.
Those cases are marked, because each one is a rule that looks unnecessary until it is not.
"""

from decimal import Decimal

from quookly.contracts.matching import Named, Resemblance
from quookly.engines import matching


def entry(slug: str, *names: str) -> Named:
    return Named(slug=slug, names=names)


class TestTheSameNameWrittenDifferently:
    def test_accents_do_not_matter(self) -> None:
        found = matching.resembling("creme fraiche", [entry("cf", "crème fraîche")])
        assert [(one.slug, one.reason) for one in found] == [("cf", Resemblance.SAME_SPELLING)]

    def test_case_does_not_matter(self) -> None:
        found = matching.resembling("PLAIN FLOUR", [entry("pf", "plain flour")])
        assert found[0].confidence == Decimal("1")

    def test_word_order_does_not_matter(self) -> None:
        found = matching.resembling("turkey breast", [entry("bt", "breast turkey")])
        assert [one.slug for one in found] == ["bt"]

    def test_punctuation_does_not_matter(self) -> None:
        found = matching.resembling("brown sugar", [entry("bs", "sugar, brown")])
        assert [one.slug for one in found] == ["bs"]

    def test_a_spelling_slip_is_caught(self) -> None:
        """`pizza doug` is in the shipped registry, beside `pizza dough`."""
        found = matching.resembling("pizza dough", [entry("pd", "pizza doug")])
        assert [one.slug for one in found] == ["pd"]

    def test_a_plural_is_caught(self) -> None:
        found = matching.resembling("brussels sprouts", [entry("bs", "brussel sprouts")])
        assert [one.slug for one in found] == ["bs"]

    def test_an_alias_matches_as_well_as_the_canonical_name(self) -> None:
        found = matching.resembling("cornstarch", [entry("cf", "cornflour", "cornstarch")])
        assert found[0].name == "cornstarch"


class TestOpposites:
    """Negation is invisible to character similarity, and these are all real rows.

    Regression: the first version scored `sweetened` against `unsweetened` at 0.98 and
    reported it as the most likely duplicate in the whole registry.
    """

    def test_an_un_prefix_is_not_a_spelling(self) -> None:
        found = matching.resembling(
            "condensed milk, sweetened", [entry("cmu", "condensed milk, unsweetened")]
        )
        assert found == []

    def test_an_explicit_not_is_not_a_spelling(self) -> None:
        found = matching.resembling(
            "pineapple in juice, canned, drained",
            [entry("p", "pineapple in juice, canned, not drained")],
        )
        assert found == []

    def test_without_reverses_a_meaning(self) -> None:
        found = matching.resembling("yoghurt with sugar", [entry("y", "yoghurt without sugar")])
        assert found == []

    def test_free_reverses_a_meaning(self) -> None:
        found = matching.resembling("gluten bread", [entry("g", "gluten free bread")])
        assert found == []


class TestDifferentFoods:
    """The other half of the first version's failure: long agreeing descriptions.

    `peach with sweetener, canned, drained` and `pear with sweetener, canned, drained`
    are 0.96 alike character by character, and are different fruits. Comparing word by
    word is what fixes it: words that differ have to differ.
    """

    def test_one_differing_word_is_not_outvoted_by_a_long_tail(self) -> None:
        found = matching.resembling(
            "peach with sweetener, canned, drained",
            [entry("pear", "pear with sweetener, canned, drained")],
        )
        assert found == []

    def test_two_drinks_described_alike_are_not_one_drink(self) -> None:
        found = matching.resembling(
            "oat drink, plain, with calcium and vitamin fortified",
            [entry("soya", "soya drink, plain, with calcium and vitamin fortified")],
        )
        assert found == []

    def test_unrelated_names_do_not_match(self) -> None:
        assert matching.resembling("saffron", [entry("bf", "unsalted butter")]) == []


class TestNumbersDistinguish:
    """Regression: the first version dropped digits, reasoning that they would swamp the
    comparison. It was backwards — in this registry the number *is* the distinction, and
    dropping it made every strength of wine a duplicate of every other."""

    def test_two_strengths_of_cheese_are_two_cheeses(self) -> None:
        found = matching.resembling(
            "at least 15% fidm appenzeller", [entry("a45", "at least 45% fidm appenzeller")]
        )
        assert found == []

    def test_two_strengths_of_wine_are_two_wines(self) -> None:
        found = matching.resembling("11 vol% wine white", [entry("w125", "12.5 vol% wine white")])
        assert found == []

    def test_the_same_strength_still_matches(self) -> None:
        found = matching.resembling("45% fidm brie", [entry("b", "brie, 45% fidm")])
        assert [one.slug for one in found] == ["b"]


class TestReporting:
    def test_the_best_spelling_of_an_entry_is_the_one_reported(self) -> None:
        found = matching.resembling("plain flour", [entry("pf", "wheat flour", "plain flour")])
        assert found[0].name == "plain flour"

    def test_an_entry_is_reported_once_however_many_names_match(self) -> None:
        found = matching.resembling("plain flour", [entry("pf", "plain flour", "flour, plain")])
        assert len(found) == 1

    def test_results_come_back_best_first(self) -> None:
        found = matching.resembling(
            "plain flour",
            [entry("near", "flour, plain"), entry("exact", "plain flour")],
            at_least=Decimal("0.5"),
        )
        assert [one.slug for one in found] == ["exact", "near"]

    def test_the_limit_is_honoured(self) -> None:
        candidates = [entry(f"e{index}", "plain flour") for index in range(10)]
        assert len(matching.resembling("plain flour", candidates, limit=3)) == 3

    def test_a_higher_bar_reports_less(self) -> None:
        candidates = [entry("near", "green peas and carrots, canned")]
        assert matching.resembling("green peas, canned", candidates, at_least=Decimal("0.5"))
        assert matching.resembling("green peas, canned", candidates, at_least=Decimal("0.99")) == []

    def test_nothing_to_compare_reports_nothing(self) -> None:
        assert matching.resembling("plain flour", []) == []

    def test_an_empty_name_reports_nothing(self) -> None:
        assert matching.resembling("", [entry("pf", "plain flour")]) == []


class TestFindingDuplicates:
    def test_a_pair_written_two_ways_is_found(self) -> None:
        found = matching.duplicates([entry("a", "brown sugar"), entry("b", "sugar, brown")])
        assert [(one.slug, one.other) for one in found] == [("a", "b")]

    def test_a_pair_is_reported_once_not_twice(self) -> None:
        found = matching.duplicates([entry("a", "brown sugar"), entry("b", "sugar, brown")])
        assert len(found) == 1

    def test_an_entry_is_not_its_own_duplicate(self) -> None:
        assert matching.duplicates([entry("a", "brown sugar")]) == []

    def test_different_foods_are_not_reported(self) -> None:
        assert matching.duplicates([entry("a", "plain flour"), entry("b", "whole milk")]) == []

    def test_opposites_are_not_reported(self) -> None:
        found = matching.duplicates(
            [entry("a", "condensed milk, sweetened"), entry("b", "condensed milk, unsweetened")]
        )
        assert found == []

    def test_the_report_is_stable_between_runs(self) -> None:
        """Same input, same order: an admin working through a list should not find it
        reshuffled underneath them."""
        entries = [
            entry("a", "brown sugar"),
            entry("b", "sugar, brown"),
            entry("c", "white sugar"),
            entry("d", "sugar, white"),
        ]
        assert matching.duplicates(entries) == matching.duplicates(list(reversed(entries)))

    def test_the_limit_is_honoured(self) -> None:
        entries = [entry(f"e{index}", f"sugar, brown {index // 2}") for index in range(10)]
        assert len(matching.duplicates(entries, limit=2)) == 2

    def test_an_empty_registry_has_no_duplicates(self) -> None:
        assert matching.duplicates([]) == []
