"""The only part of the bulk registry import where being wrong is dangerous.

The asymmetry these tests exist to hold: adding an allergen costs a cook a dish, declaring
a *complete* set that is wrong can put an allergen on a plate. So "contains" is judged
leniently and "contains nothing else" strictly (ADR-006).
"""

import sys
from pathlib import Path

import pytest

from quookly.contracts.ingredient import Allergen

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "seed"))

import allergens  # noqa: E402


class TestWhatItFinds:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Whole milk, pasteurized", Allergen.MILK),
            ("Cream cheese", Allergen.MILK),
            ("Egg, raw", Allergen.EGGS),
            ("Wheat flour, white, type 400", Allergen.GLUTEN),
            ("Tofu, plain", Allergen.SOYBEANS),
            ("Peanut, roasted", Allergen.PEANUTS),
            ("Hazelnut", Allergen.TREE_NUTS),
            ("Sesame seeds", Allergen.SESAME),
            ("Celeriac, raw", Allergen.CELERY),
            ("Mustard, medium hot", Allergen.MUSTARD),
            ("Salmon, raw", Allergen.FISH),
            ("Prawn, cooked", Allergen.CRUSTACEANS),
            ("Mussel, raw", Allergen.MOLLUSCS),
        ],
    )
    def test_a_name_that_names_its_allergen(self, name: str, expected: Allergen) -> None:
        assert expected in allergens.of(name, "Various").allergens

    def test_a_cheese_is_milk_even_when_its_name_says_nothing(self) -> None:
        """Emmentaler, Gruyère, Sbrinz. The category is the allergen here, and a name
        table alone would let a hard cheese through as dairy-free."""
        found = allergens.of("Sbrinz", "Milk and dairy products/Hard cheese")
        assert Allergen.MILK in found.allergens

    def test_a_sea_fish_is_fish_whatever_it_is_called(self) -> None:
        assert Allergen.FISH in allergens.of("Rascasse", "Fish/Sea fish").allergens


class TestWhenItWillNotCommit:
    """The half that matters. `classified=False` is stored as absence, which reads as
    "nobody has looked" — never as "safe"."""

    def test_a_sausage_is_not_declared_complete(self) -> None:
        """What else went into a sausage is not knowable from the word "sausage": rusk,
        mustard, milk powder and celery are all ordinary in one."""
        assert not allergens.of(
            "Bratwurst, veal", "Sausages and cold meats/Raw sausage products"
        ).classified

    def test_a_sauce_is_not_declared_complete(self) -> None:
        assert not allergens.of("Barbecue sauce", "Various/Sauces").classified

    def test_a_bread_is_not_declared_complete(self) -> None:
        """It has gluten, and it may also have sesame, milk or soy. Naming one is not the
        same as having looked for all fourteen."""
        found = allergens.of(
            "Bread, wheat, white", "Bread, flakes and breakfast cereals/Bread and bread products"
        )
        assert Allergen.GLUTEN in found.allergens
        assert not found.classified

    def test_a_row_filed_under_two_groups_is_only_as_certain_as_the_vaguest(self) -> None:
        """ "Fresh fruit" we can answer for; "Sauces" we cannot, and the row is both."""
        assert not allergens.of("Apple purée", "Fruit/Fresh fruit;Various/Sauces").classified

    def test_a_row_with_no_category_is_not_declared_complete(self) -> None:
        assert not allergens.of("Something", None).classified


class TestWhenItWillCommit:
    def test_a_raw_vegetable_is_answered_completely(self) -> None:
        found = allergens.of("Carrot, raw", "Vegetables/Fresh vegetables")
        assert found.classified
        assert found.allergens == frozenset()

    def test_celery_is_still_caught_inside_a_group_answered_completely(self) -> None:
        """The reason vegetables can be declared complete at all: the only declarable
        allergens among them name themselves."""
        found = allergens.of("Celeriac, raw", "Vegetables/Fresh vegetables")
        assert found.classified
        assert found.allergens == frozenset({Allergen.CELERY})

    def test_a_plain_cut_of_meat_is_answered_completely(self) -> None:
        found = allergens.of("Beef, filet, raw", "Meat and offal/Beef")
        assert found.classified
        assert found.allergens == frozenset()

    def test_an_oil_is_answered_completely_and_sesame_oil_still_says_sesame(self) -> None:
        plain = allergens.of("Olive oil", "Fats and oils/Oils")
        assert plain.classified
        assert plain.allergens == frozenset()

        seeded = allergens.of("Sesame oil", "Fats and oils/Oils")
        assert seeded.classified
        assert seeded.allergens == frozenset({Allergen.SESAME})


class TestComposedFoods:
    """The failure this class was written for: a game terrine is filed under
    "Meat and offal/Game" and came back declared allergen-free. It is a terrine — egg,
    cream and pistachio are ordinary in one — and the category cannot know."""

    @pytest.mark.parametrize(
        "name",
        [
            "Game meat terrine",
            "Veal, escalope, breaded",
            "Chicken nuggets",
            "Beef burger patty",
            "Pork sausage, raw",
        ],
    )
    def test_a_composed_food_is_never_declared_complete(self, name: str) -> None:
        assert not allergens.of(name, "Meat and offal/Game").classified

    def test_a_plain_cut_in_the_same_category_still_is(self) -> None:
        assert allergens.of("Venison, leg, raw", "Meat and offal/Game").classified

    def test_breaded_means_gluten_even_where_nothing_else_is_known(self) -> None:
        """Breadcrumbs are wheat unless a label says otherwise. Adding the allergen is the
        safe direction, so a keyword is enough."""
        found = allergens.of("Veal, escalope, breaded", "Meat and offal/Veal")
        assert Allergen.GLUTEN in found.allergens
        assert not found.classified
