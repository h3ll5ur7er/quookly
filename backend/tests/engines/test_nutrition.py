"""Working out what a recipe contains (V6, UC-2.3).

A rule engine: profiles and preferences arrive as arguments, so the two decisions here are
a table of cases rather than a fixture.

Those two decisions carry the weight. **Which table answers** decides whether a Swiss cook
is told about American fortification (ADR-045), and **what cannot be counted** decides
whether a number is a total or a floor — a figure that quietly leaves out the butter is
worse than no figure.
"""

from decimal import Decimal

import pytest

from quookly.contracts.ingredient import Ingredient, IngredientKind, Origin
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.nutrition import Nutrient, NutrientProfile, NutritionSource
from quookly.contracts.recipe import IngredientLine
from quookly.engines import nutrition

FLOUR, BUTTER, EGG, SALT = 1, 2, 3, 4


def ingredient(
    ingredient_id: int,
    slug: str,
    kind: IngredientKind = IngredientKind.POWDER,
    density: str | None = "0.53",
    piece_grams: str | None = None,
) -> Ingredient:
    return Ingredient(
        id=ingredient_id,
        slug=slug,
        kind=kind,
        name=slug,
        density=None if density is None else Decimal(density),
        origin=Origin.SEED,
        piece_grams=None if piece_grams is None else Decimal(piece_grams),
    )


def line(entry: Ingredient, quantity: Quantity | None, optional: bool = False) -> IngredientLine:
    return IngredientLine(
        id=entry.id,
        ingredient=entry,
        quantity=quantity,
        preparation=None,
        optional=optional,
    )


def profile(
    ingredient_id: int,
    source: NutritionSource = NutritionSource.SWISS,
    **amounts: str,
) -> NutrientProfile:
    return NutrientProfile(
        ingredient_id=ingredient_id,
        source=source,
        reference=f"{source.value}:{ingredient_id}",
        amounts={Nutrient(name): Decimal(value) for name, value in amounts.items()},
    )


SWISS_ORDER = [NutritionSource.SWISS, NutritionSource.CIQUAL, NutritionSource.USDA]


class TestCounting:
    def test_a_hundred_grams_is_the_profile_itself(self) -> None:
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM))],
            [profile(FLOUR, protein="12", energy_kcal="345")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.PROTEIN] == Decimal(12)
        assert counted.amounts[Nutrient.ENERGY_KCAL] == Decimal(345)

    def test_a_quantity_scales_the_profile(self) -> None:
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(250), Unit.GRAM))],
            [profile(FLOUR, protein="12")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.PROTEIN] == Decimal(30)

    def test_a_kilogram_is_grams(self) -> None:
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(1), Unit.KILOGRAM))],
            [profile(FLOUR, protein="12")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.PROTEIN] == Decimal(120)

    def test_a_volume_is_weighed_through_the_density(self) -> None:
        """Every table publishes per 100 g, and a recipe says "300 ml". The registry's
        density is what joins them, and it is already there for unit conversion."""
        milk = ingredient(FLOUR, "milk", IngredientKind.LIQUID, density="1.03")
        counted = nutrition.count(
            [line(milk, Quantity(Decimal(200), Unit.MILLILITRE))],
            [profile(FLOUR, protein="3.3")],
            SWISS_ORDER,
        )
        assert counted is not None
        # 200 ml of milk weighs 206 g, so 3.3 g per 100 g comes to 6.798.
        assert counted.amounts[Nutrient.PROTEIN] == Decimal("6.798")

    def test_a_countable_is_weighed_through_what_one_weighs(self) -> None:
        egg = ingredient(EGG, "egg", IngredientKind.COUNTABLE, density=None, piece_grams="55")
        counted = nutrition.count(
            [line(egg, Quantity(Decimal(2), Unit.PIECE))],
            [profile(EGG, protein="12.6")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.PROTEIN] == Decimal("13.86")

    def test_several_lines_add_up(self) -> None:
        counted = nutrition.count(
            [
                line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM)),
                line(ingredient(BUTTER, "butter"), Quantity(Decimal(100), Unit.GRAM)),
            ],
            [profile(FLOUR, protein="12"), profile(BUTTER, protein="0.7")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.PROTEIN] == Decimal("12.7")

    def test_a_nutrient_only_one_table_measured_is_still_added(self) -> None:
        """Absent is not zero. A flour with no fibre figure does not make the recipe's
        fibre smaller; it makes the fibre figure a floor."""
        counted = nutrition.count(
            [
                line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM)),
                line(ingredient(BUTTER, "butter"), Quantity(Decimal(100), Unit.GRAM)),
            ],
            [profile(FLOUR, fibre="3.3"), profile(BUTTER, protein="0.7")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.FIBRE] == Decimal("3.3")


class TestWhichTableAnswers:
    def test_the_first_source_in_the_order_wins(self) -> None:
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM))],
            [
                profile(FLOUR, NutritionSource.USDA, protein="10.3"),
                profile(FLOUR, NutritionSource.SWISS, protein="12"),
            ],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.PROTEIN] == Decimal(12)
        assert counted.sources == [NutritionSource.SWISS]

    def test_a_later_source_answers_where_the_first_has_nothing(self) -> None:
        """Which is the whole point of a cascade: the Swiss table is 1200 foods and the
        American one is thousands, so the one that is better where it applies goes first
        and the one that answers for anything goes last."""
        counted = nutrition.count(
            [line(ingredient(FLOUR, "quinoa"), Quantity(Decimal(100), Unit.GRAM))],
            [profile(FLOUR, NutritionSource.USDA, protein="14.1")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.PROTEIN] == Decimal("14.1")
        assert counted.sources == [NutritionSource.USDA]

    def test_a_source_not_in_the_order_does_not_answer(self) -> None:
        """An instance that has turned a table off has turned it off."""
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM))],
            [profile(FLOUR, NutritionSource.COFID, protein="9.4")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts == {}
        assert counted.uncounted == ["flour"]

    def test_nutrients_are_never_taken_from_two_tables_at_once(self) -> None:
        """A value with its protein from Bern and its fibre from Beltsville is a number
        nobody measured. One table answers for one ingredient, whole."""
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM))],
            [
                profile(FLOUR, NutritionSource.SWISS, protein="12"),
                profile(FLOUR, NutritionSource.USDA, protein="10.3", fibre="2.7"),
            ],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts == {Nutrient.PROTEIN: Decimal(12)}

    def test_every_table_that_answered_is_named(self) -> None:
        counted = nutrition.count(
            [
                line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM)),
                line(ingredient(BUTTER, "quinoa"), Quantity(Decimal(100), Unit.GRAM)),
            ],
            [
                profile(FLOUR, NutritionSource.SWISS, protein="12"),
                profile(BUTTER, NutritionSource.USDA, protein="14.1"),
            ],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.sources == [NutritionSource.SWISS, NutritionSource.USDA]


class TestWhatCannotBeCounted:
    def test_an_ingredient_no_table_answers_for_makes_the_total_a_floor(self) -> None:
        counted = nutrition.count(
            [
                line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM)),
                line(ingredient(BUTTER, "sourdough starter"), Quantity(Decimal(50), Unit.GRAM)),
            ],
            [profile(FLOUR, protein="12")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.at_least
        assert counted.uncounted == ["sourdough starter"]

    def test_a_line_with_no_quantity_cannot_be_counted(self) -> None:
        """Salt to taste. Twice as much to taste is still to taste, and there is no weight
        to put against a profile."""
        counted = nutrition.count(
            [line(ingredient(SALT, "salt"), None)],
            [profile(SALT, salt="100")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.at_least
        assert counted.uncounted == ["salt"]

    def test_a_volume_with_no_density_cannot_be_weighed(self) -> None:
        vague = ingredient(FLOUR, "stock", IngredientKind.LIQUID, density=None)
        counted = nutrition.count(
            [line(vague, Quantity(Decimal(200), Unit.MILLILITRE))],
            [profile(FLOUR, protein="1")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.uncounted == ["stock"]

    def test_a_countable_with_no_weight_cannot_be_weighed(self) -> None:
        """An egg has no grams until somebody says how much one weighs. Inventing a figure
        would put a number on a label that nobody measured."""
        egg = ingredient(EGG, "egg", IngredientKind.COUNTABLE, density=None)
        counted = nutrition.count(
            [line(egg, Quantity(Decimal(2), Unit.PIECE))],
            [profile(EGG, protein="12.6")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.uncounted == ["egg"]

    def test_a_recipe_that_can_be_counted_whole_is_not_a_floor(self) -> None:
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM))],
            [profile(FLOUR, protein="12")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert not counted.at_least
        assert counted.uncounted == []

    def test_an_optional_line_is_not_counted_and_is_not_a_gap(self) -> None:
        """A recipe without it is a real version of the dish — the same reading the
        shopping list takes, so the two cannot disagree about what is being made."""
        counted = nutrition.count(
            [
                line(ingredient(FLOUR, "flour"), Quantity(Decimal(100), Unit.GRAM)),
                line(ingredient(BUTTER, "butter"), Quantity(Decimal(50), Unit.GRAM), optional=True),
            ],
            [profile(FLOUR, protein="12"), profile(BUTTER, protein="0.7")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts[Nutrient.PROTEIN] == Decimal(12)
        assert not counted.at_least
        assert counted.uncounted == []

    def test_a_recipe_with_nothing_in_it_says_nothing(self) -> None:
        assert nutrition.count([], [], SWISS_ORDER) is None

    def test_a_recipe_nothing_answers_for_says_why_rather_than_nothing(self) -> None:
        """Zeroes would read as a food made of air, and silence tells a cook nothing they
        can act on. Naming the gap is the only one of the three that helps."""
        counted = nutrition.count(
            [line(ingredient(FLOUR, "sourdough starter"), Quantity(Decimal(50), Unit.GRAM))],
            [],
            SWISS_ORDER,
        )
        assert counted is not None
        assert counted.amounts == {}
        assert counted.uncounted == ["sourdough starter"]
        assert counted.at_least


class TestPerServing:
    def test_a_recipe_that_serves_four(self) -> None:
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(400), Unit.GRAM))],
            [profile(FLOUR, protein="12")],
            SWISS_ORDER,
        )
        assert counted is not None
        each = nutrition.per_serving(counted, Decimal(4))
        assert each is not None
        assert each.amounts[Nutrient.PROTEIN] == Decimal(12)

    def test_a_recipe_that_does_not_say_how_many_it_feeds(self) -> None:
        """How much is in the tray is knowable; how much is on a plate is not (ADR-030)."""
        counted = nutrition.count(
            [line(ingredient(FLOUR, "flour"), Quantity(Decimal(400), Unit.GRAM))],
            [profile(FLOUR, protein="12")],
            SWISS_ORDER,
        )
        assert counted is not None
        assert nutrition.per_serving(counted, None) is None

    def test_a_floor_stays_a_floor_once_divided(self) -> None:
        counted = nutrition.count(
            [
                line(ingredient(FLOUR, "flour"), Quantity(Decimal(400), Unit.GRAM)),
                line(ingredient(BUTTER, "mystery"), Quantity(Decimal(50), Unit.GRAM)),
            ],
            [profile(FLOUR, protein="12")],
            SWISS_ORDER,
        )
        assert counted is not None
        each = nutrition.per_serving(counted, Decimal(4))
        assert each is not None
        assert each.at_least


@pytest.mark.parametrize(
    ("nutrient", "unit"),
    [
        (Nutrient.ENERGY_KJ, "kJ"),
        (Nutrient.ENERGY_KCAL, "kcal"),
        (Nutrient.PROTEIN, "g"),
        (Nutrient.SALT, "g"),
    ],
)
def test_what_each_nutrient_is_measured_in(nutrient: Nutrient, unit: str) -> None:
    assert nutrient.unit == unit
