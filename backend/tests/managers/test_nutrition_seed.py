"""The published figures, from the shelf to the screen (UC-2.3, FR-20, ADR-045).

The chain this covers is the one nothing else does: a Swiss table's published rows, matched
to this instance's registry, weighed against a recipe's quantities, and reported with the
credit that using them obliges.

Values are asserted against the *published* figures rather than against whatever the code
produced. A test that agrees with the implementation about butter proves nothing; one that
agrees with the Federal Food Safety and Veterinary Office proves the number is real.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.nutrition import Nutrient, NutritionSource
from quookly.managers import recipe as recipe_manager
from quookly.managers import seed
from quookly.utilities.configuration import get_settings, preferred_sources

ENGLISH = "en-GB"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def stocked() -> None:
    await seed.stock_registry()
    await seed.stock_nutrition()


@pytest.fixture
async def cook_id() -> int:
    cook = await cook_access.register("chef@example.com", "Emanuel", "hash")
    return cook.id


class TestTheShippedTable:
    async def test_the_registry_gets_its_figures(self, stocked: None) -> None:
        ids = await registry.ids_by_slug(["plain-flour"])
        profiles = await registry.profiles_for([ids["plain-flour"]])
        assert [one.source for one in profiles] == [NutritionSource.SWISS]

    async def test_the_figures_are_the_published_ones(self, stocked: None) -> None:
        """Wheat flour, white, type 400 — as the FSVO publishes it, per 100 g."""
        ids = await registry.ids_by_slug(["plain-flour"])
        flour = (await registry.profiles_for([ids["plain-flour"]]))[0]
        assert flour.amounts[Nutrient.PROTEIN] == Decimal("11.5")
        assert flour.amounts[Nutrient.ENERGY_KCAL] == Decimal("346")
        assert flour.amounts[Nutrient.SALT] == Decimal("0")

    async def test_a_number_can_be_traced_to_the_row_it_came_from(self, stocked: None) -> None:
        """Which matters more than usual here: the mapping from "plain flour" to one of
        four wheat flours by ash content is a judgement somebody made."""
        ids = await registry.ids_by_slug(["plain-flour"])
        flour = (await registry.profiles_for([ids["plain-flour"]]))[0]
        assert flour.reference == "205 Wheat flour, white, type 400"

    async def test_what_the_table_does_not_carry_is_absent(self, stocked: None) -> None:
        """Baking powder is not in the Swiss database. That is the cascade working, not a
        bug — another source answers, or the recipe says it could not count it."""
        ids = await registry.ids_by_slug(["baking-powder"])
        assert await registry.profiles_for([ids["baking-powder"]]) == []

    async def test_seeding_twice_does_not_double_the_figures(self, stocked: None) -> None:
        await seed.stock_nutrition()
        ids = await registry.ids_by_slug(["plain-flour"])
        flour = (await registry.profiles_for([ids["plain-flour"]]))[0]
        assert flour.amounts[Nutrient.PROTEIN] == Decimal("11.5")

    async def test_a_withdrawn_figure_disappears_rather_than_lingering(self, stocked: None) -> None:
        """Restated wholesale. These are somebody else's measurements, and a corrected
        table that still showed the old number would be worse than no table."""
        ids = await registry.ids_by_slug(["plain-flour"])
        thinner = (await registry.profiles_for([ids["plain-flour"]]))[0]
        await registry.record_profile(
            type(thinner)(
                ingredient_id=thinner.ingredient_id,
                source=thinner.source,
                reference=thinner.reference,
                amounts={Nutrient.PROTEIN: Decimal("11.5")},
            )
        )
        again = (await registry.profiles_for([ids["plain-flour"]]))[0]
        assert set(again.amounts) == {Nutrient.PROTEIN}


class TestARecipeOnTheScreen:
    async def test_a_starter_recipe_reports_what_it_contains(
        self, stocked: None, cook_id: int
    ) -> None:
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id, ENGLISH)
        shortbread = next(one for one in listed if one.title == "Shortbread")

        presented = await recipe_manager.present(shortbread.id, cook_id, ENGLISH)
        assert presented is not None
        assert presented.nutrition is not None
        assert presented.nutrition.per_recipe

    async def test_the_figures_are_worked_out_from_the_quantities(
        self, stocked: None, cook_id: int
    ) -> None:
        """225 g of butter at 82.3 g of fat per 100 g is 185.2 g, and the rest of the
        shortbread adds a little more. Arithmetic on published numbers, not a lookup."""
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id, ENGLISH)
        shortbread = next(one for one in listed if one.title == "Shortbread")

        presented = await recipe_manager.present(shortbread.id, cook_id, ENGLISH)
        assert presented is not None
        assert presented.nutrition is not None
        fat = next(one for one in presented.nutrition.per_recipe if one.nutrient is Nutrient.FAT)
        assert Decimal(fat.amount) > Decimal(185)
        assert fat.unit == "g"

    async def test_it_says_who_measured_it(self, stocked: None, cook_id: int) -> None:
        """FR-20. The Swiss grant makes attribution mandatory, so this is a requirement
        rather than a courtesy."""
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id, ENGLISH)
        shortbread = next(one for one in listed if one.title == "Shortbread")

        presented = await recipe_manager.present(shortbread.id, cook_id, ENGLISH)
        assert presented is not None
        assert presented.nutrition is not None
        assert [credit.publisher for credit in presented.nutrition.credits] == [
            "Federal Food Safety and Veterinary Office (FSVO)"
        ]

    async def test_per_serving_follows_from_what_the_recipe_says_it_serves(
        self, stocked: None, cook_id: int
    ) -> None:
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id, ENGLISH)
        shortbread = next(one for one in listed if one.title == "Shortbread")

        presented = await recipe_manager.present(shortbread.id, cook_id, ENGLISH)
        assert presented is not None
        assert presented.nutrition is not None
        assert presented.nutrition.per_serving is not None

        whole = {one.nutrient: Decimal(one.amount) for one in presented.nutrition.per_recipe}
        each = {one.nutrient: Decimal(one.amount) for one in presented.nutrition.per_serving}
        # Shortbread serves eight.
        assert each[Nutrient.FAT] == pytest.approx(whole[Nutrient.FAT] / 8, abs=Decimal("0.1"))

    async def test_scaling_the_recipe_scales_what_is_in_it(
        self, stocked: None, cook_id: int
    ) -> None:
        """Unlike the time it takes, this one really is arithmetic: twice the tray is
        twice the butter."""
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id, ENGLISH)
        shortbread = next(one for one in listed if one.title == "Shortbread")

        once = await recipe_manager.present(shortbread.id, cook_id, ENGLISH)
        twice = await recipe_manager.present(shortbread.id, cook_id, ENGLISH, Decimal(32))
        assert once is not None and twice is not None
        assert once.nutrition is not None and twice.nutrition is not None

        def fat(view: object) -> Decimal:
            return next(
                Decimal(one.amount)
                for one in view.per_recipe  # type: ignore[attr-defined]
                if one.nutrient is Nutrient.FAT
            )

        assert fat(twice.nutrition) == pytest.approx(fat(once.nutrition) * 2, abs=Decimal("0.2"))

    async def test_an_ingredient_no_table_answers_for_makes_it_a_floor(
        self, stocked: None, cook_id: int
    ) -> None:
        """Pancakes need baking powder, and the Swiss table has none. The cook is told
        which ingredient is missing rather than handed a total that quietly leaves it out."""
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id, ENGLISH)
        pancakes = next(one for one in listed if "Pancakes" in one.title)

        presented = await recipe_manager.present(pancakes.id, cook_id, ENGLISH)
        assert presented is not None
        assert presented.nutrition is not None
        assert presented.nutrition.at_least
        assert "baking powder" in presented.nutrition.uncounted

    async def test_an_egg_cannot_be_weighed_until_somebody_says_what_one_weighs(
        self, stocked: None, cook_id: int
    ) -> None:
        """No table Quookly reads publishes a portion weight, so this is unset and the
        gap is named rather than filled with an invented figure."""
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id, ENGLISH)
        pancakes = next(one for one in listed if "Pancakes" in one.title)

        presented = await recipe_manager.present(pancakes.id, cook_id, ENGLISH)
        assert presented is not None
        assert presented.nutrition is not None
        assert "egg" in presented.nutrition.uncounted

    async def test_saying_what_one_weighs_lets_it_be_counted(
        self, stocked: None, cook_id: int
    ) -> None:
        await registry.weigh_pieces("egg", Decimal("55"))
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id, ENGLISH)
        pancakes = next(one for one in listed if "Pancakes" in one.title)

        presented = await recipe_manager.present(pancakes.id, cook_id, ENGLISH)
        assert presented is not None
        assert presented.nutrition is not None
        assert "egg" not in presented.nutrition.uncounted


class TestWhichTablesThisInstanceBelieves:
    def test_the_shipped_order_prefers_the_tables_measured_nearest(self) -> None:
        assert preferred_sources()[0] is NutritionSource.SWISS
        assert preferred_sources()[-1] is NutritionSource.USDA

    def test_an_instance_can_say_otherwise(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("QUOOKLY_NUTRITION_SOURCES", "usda,swiss")
        get_settings.cache_clear()
        assert preferred_sources() == [NutritionSource.USDA, NutritionSource.SWISS]

    def test_a_name_nobody_recognises_costs_one_table_rather_than_the_instance(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("QUOOKLY_NUTRITION_SOURCES", "swiss, mystery ,usda")
        get_settings.cache_clear()
        assert preferred_sources() == [NutritionSource.SWISS, NutritionSource.USDA]
