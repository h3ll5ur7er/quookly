"""Which recipe to suggest, and why (V10, UC-3.3, UC-3.4).

A rule engine: candidates arrive as counts, so the whole ordering policy is a table of
cases with nothing to fetch.

The judgement being made is a small one and it is worth stating: **a suggestion earns its
place by saving something.** Food about to go off is the thing this product exists to
reduce, so a recipe that uses it comes before one the cook merely happens to have the
ingredients for — and both come before one that means a trip to the shop.
"""

from decimal import Decimal

from quookly.contracts.discovery import Candidate, Reason
from quookly.engines import ranking


def candidate(
    recipe_id: int,
    have: int = 5,
    needs: int = 5,
    pressing: list[str] | None = None,
    suitable: bool | None = None,
    relevance: str | None = None,
) -> Candidate:
    return Candidate(
        recipe_id=recipe_id,
        have=have,
        needs=needs,
        pressing=pressing or [],
        suitable=suitable,
        relevance=None if relevance is None else Decimal(relevance),
    )


def order(*candidates: Candidate) -> list[int]:
    return [one.recipe_id for one in ranking.rank(list(candidates))]


class TestWhatComesFirst:
    def test_using_something_that_needs_eating_beats_having_everything(self) -> None:
        """The whole point. A cook with a full cupboard has plenty of options; the spinach
        going off on Thursday is the one that costs money if it is ignored."""
        assert order(
            candidate(1, have=5, needs=5),
            candidate(2, have=4, needs=5, pressing=["spinach"]),
        ) == [2, 1]

    def test_using_two_pressing_things_beats_using_one(self) -> None:
        assert order(
            candidate(1, have=5, needs=5, pressing=["spinach"]),
            candidate(2, have=5, needs=5, pressing=["spinach", "cream"]),
        ) == [2, 1]

    def test_having_everything_beats_a_trip_to_the_shop(self) -> None:
        assert order(candidate(1, have=3, needs=5), candidate(2, have=5, needs=5)) == [2, 1]

    def test_more_of_it_in_the_cupboard_comes_first(self) -> None:
        assert order(candidate(1, have=1, needs=5), candidate(2, have=4, needs=5)) == [2, 1]

    def test_a_bigger_recipe_is_not_punished_for_being_bigger(self) -> None:
        """Coverage is a proportion. Ten of twelve is better placed than two of two is not
        — a recipe of two ingredients you have is a cup of tea."""
        assert order(candidate(1, have=2, needs=2), candidate(2, have=10, needs=12)) == [1, 2]

    def test_the_order_does_not_depend_on_the_order_given(self) -> None:
        """Without a tiebreak the answer would depend on how rows happened to arrive, and
        the same question would get two answers."""
        assert order(candidate(2), candidate(1)) == order(candidate(1), candidate(2))


class TestWhatSomebodyCannotEat:
    def test_a_recipe_nobody_at_the_table_can_eat_goes_last(self) -> None:
        assert order(
            candidate(1, have=1, needs=5, suitable=False),
            candidate(2, have=1, needs=5, suitable=True),
        ) == [2, 1]

    def test_it_goes_behind_even_a_recipe_that_saves_nothing(self) -> None:
        """Ranked down rather than hidden (ADR-010): a cook may still want it, and the
        badge says why. Leading with it would be the interface making a decision about
        somebody's allergy."""
        assert order(
            candidate(1, have=5, needs=5, pressing=["spinach"], suitable=False),
            candidate(2, have=1, needs=5, suitable=True),
        ) == [2, 1]

    def test_nobody_described_is_not_the_same_as_suitable(self) -> None:
        """An empty household satisfies every constraint there is, and treating that as a
        clean bill of health would be a reassurance about a question nobody asked."""
        ranked = ranking.rank([candidate(1, suitable=None)])
        assert Reason.NOT_FOR_EVERYONE not in ranked[0].reasons


class TestWhenSomethingWasTyped:
    def test_what_matched_best_comes_first(self) -> None:
        """A search is a question, and the answer to it beats a suggestion nobody asked
        for. Coverage and expiry break ties rather than overturn the match."""
        assert order(
            candidate(1, have=5, needs=5, pressing=["spinach"], relevance="1"),
            candidate(2, have=0, needs=5, relevance="9"),
        ) == [2, 1]

    def test_things_that_matched_alike_are_split_by_what_they_save(self) -> None:
        assert order(
            candidate(1, have=5, needs=5, relevance="5"),
            candidate(2, have=5, needs=5, pressing=["spinach"], relevance="5"),
        ) == [2, 1]


class TestWhatItSays:
    def test_having_everything_is_worth_saying(self) -> None:
        ranked = ranking.rank([candidate(1, have=5, needs=5)])
        assert Reason.HAVE_EVERYTHING in ranked[0].reasons
        assert ranked[0].missing == 0

    def test_having_most_of_it_is_worth_saying_too(self) -> None:
        ranked = ranking.rank([candidate(1, have=4, needs=5)])
        assert Reason.HAVE_MOST in ranked[0].reasons
        assert ranked[0].missing == 1

    def test_having_hardly_any_of_it_is_not_a_reason(self) -> None:
        ranked = ranking.rank([candidate(1, have=1, needs=5)])
        assert ranked[0].reasons == []
        assert ranked[0].missing == 4

    def test_what_needs_eating_is_named_rather_than_counted(self) -> None:
        """ "Uses 2 things that need eating" does not tell a cook whether to bother."""
        ranked = ranking.rank([candidate(1, pressing=["spinach", "double cream"])])
        assert ranked[0].pressing == ["spinach", "double cream"]
        assert Reason.USES_SOON in ranked[0].reasons

    def test_a_recipe_somebody_cannot_eat_says_so(self) -> None:
        ranked = ranking.rank([candidate(1, suitable=False)])
        assert Reason.NOT_FOR_EVERYONE in ranked[0].reasons

    def test_a_recipe_needing_nothing_at_all(self) -> None:
        """A recipe of only unmeasured lines — salt, oil for frying. Nothing to have, so
        nothing to claim about having it."""
        ranked = ranking.rank([candidate(1, have=0, needs=0)])
        assert ranked[0].reasons == []
        assert ranked[0].missing == 0


def test_nothing_to_rank() -> None:
    assert ranking.rank([]) == []
