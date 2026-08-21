"""Getting from a written ingredient name to one the registry knows (V2).

"3 large free-range eggs" is eggs. A reader that cannot see that creates a second registry
entry called "large free-range eggs" — which is not merely untidy. The new entry has never
been classified, so an egg allergy stops firing on it, and the recipe reads as *unknown*
when the registry knew the answer perfectly well.

The stripping is deliberately timid. Dropping any adjective would turn "coconut milk" into
milk and "smoked paprika" into paprika, so only words that never change *what a thing is*
are dropped — and "whole", as in whole milk, is pointedly not one of them.
"""

import pytest

from quookly.engines import interpretation


def candidates(written: str) -> list[str]:
    return interpretation.candidate_names(written)


class TestWhatIsTriedFirst:
    def test_the_name_as_written_comes_first(self) -> None:
        """The registry may know the full name, and it is the better match if it does."""
        assert candidates("large free-range eggs")[0] == "large free-range eggs"

    def test_a_name_that_needs_nothing_offers_nothing_else_first(self) -> None:
        assert candidates("plain flour")[0] == "plain flour"


class TestSizeAndQuality:
    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("large free-range eggs", "egg"),
            ("large egg", "egg"),
            ("medium onions", "onion"),
            ("organic whole milk", "whole milk"),
            ("fresh flat-leaf parsley", "flat-leaf parsley"),
            ("best dark chocolate", "dark chocolate"),
        ],
    )
    def test_words_about_the_shopping_are_dropped(self, written: str, expected: str) -> None:
        """Size and quality describe which one to buy, not what it is."""
        assert expected in candidates(written)


class TestWhatItRefusesToDrop:
    @pytest.mark.parametrize(
        ("written", "forbidden"),
        [
            ("coconut milk", "milk"),
            ("whole milk", "milk"),
            ("smoked paprika", "paprika"),
            ("plain flour", "flour"),
            ("dark chocolate", "chocolate"),
            ("soy sauce", "sauce"),
        ],
    )
    def test_an_adjective_that_changes_the_thing_stays(self, written: str, forbidden: str) -> None:
        """Coconut milk resolved to milk would attach a dairy allergen to a dairy-free
        ingredient, and would weigh it wrongly besides."""
        assert forbidden not in candidates(written)


class TestPlurals:
    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("eggs", "egg"),
            ("onions", "onion"),
            ("tomatoes", "tomato"),
            ("cherries", "cherry"),
            ("potatoes", "potato"),
        ],
    )
    def test_a_plural_is_offered_in_the_singular(self, written: str, expected: str) -> None:
        """A registry holds "egg"; a recipe asks for eggs."""
        assert expected in candidates(written)

    def test_a_word_ending_in_s_that_is_not_a_plural_is_still_offered_whole(self) -> None:
        assert "molasses" in candidates("molasses")


class TestItDoesNotLoop:
    def test_nothing_is_offered_twice(self) -> None:
        assert len(candidates("large eggs")) == len(set(candidates("large eggs")))

    def test_an_empty_name_offers_nothing(self) -> None:
        assert candidates("   ") == []
