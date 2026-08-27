"""Merging two registry entries that are the same food (Phase 7).

The operation the registry screen exists for. An import that created `plain flour` beside
a registry that already had `wheat flour` has split one ingredient in two, and every
allergen and nutrition fact then answers for half a kitchen.

Merging is the most dangerous thing in this module, because a registry entry is pointed at
from seven tables by id and from an eighth — `eater_constraint` — by *slug*, which no
foreign key protects. A merge that misses that one silently stops an allergy from firing.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel, select

from quookly.access import academy
from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine, session
from quookly.access.models import CookRow, EaterConstraintRow, EaterRow
from quookly.contracts.academy import NewPage, PageKind, Wording
from quookly.contracts.cook import Standing
from quookly.contracts.eater import AgeBand, Severity
from quookly.contracts.errors import IngredientNotRegistered, NothingToMerge
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.contracts.nutrition import Nutrient, NutrientProfile, NutritionSource
from quookly.utilities.configuration import get_settings

ENGLISH = "en-GB"
GERMAN = "de-CH"


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


async def two_entries() -> tuple[int, int]:
    """The shipped one, and the one an import invented beside it."""
    keeper = await registry.register(
        slug="wheat-flour",
        kind=IngredientKind.POWDER,
        density=Decimal("0.593"),
        names={ENGLISH: ["wheat flour"], GERMAN: ["Weizenmehl"]},
        origin=Origin.SEED,
        allergens=frozenset({Allergen.GLUTEN}),
    )
    loser = await registry.register(
        slug="plain-flour",
        kind=IngredientKind.SOLID,
        density=None,
        names={ENGLISH: ["plain flour"]},
        origin=Origin.USER,
    )
    return keeper.id, loser.id


async def a_cook() -> int:
    """An account for a page to be written by. The column is a key, so it has to exist.

    The same one every time it is asked for: a test that writes two pages wants two pages,
    not two accounts.
    """
    held = await cook_access.fetch_by_email("chef@example.com")
    if held is not None:
        assert held.id is not None
        return held.id
    made = await cook_access.register("chef@example.com", "Emanuel", "hash")
    assert made.id is not None
    return made.id


class TestWhatSurvives:
    async def test_the_loser_is_gone(self) -> None:
        await two_entries()
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        assert await registry.detail("plain-flour") is None

    async def test_the_keeper_remains(self) -> None:
        await two_entries()
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        assert await registry.detail("wheat-flour") is not None

    async def test_the_losers_names_become_spellings_of_the_keeper(self) -> None:
        """The point of merging rather than deleting: a page saying "plain flour" must
        still resolve, or the next import invents the duplicate again."""
        await two_entries()
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        found = await registry.resolve("plain flour", ENGLISH)
        assert found is not None
        assert found.slug == "wheat-flour"

    async def test_the_keepers_own_name_stays_canonical(self) -> None:
        await two_entries()
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        found = await registry.resolve("plain flour", ENGLISH)
        assert found is not None
        assert found.name == "wheat flour"

    async def test_a_spelling_both_had_does_not_collide(self) -> None:
        """`(locale, normalised)` is unique, so repointing a shared spelling would fail."""
        await two_entries()
        await registry.name_in("plain-flour", GERMAN, ["Mehl"])
        await registry.name_in("wheat-flour", GERMAN, ["Mehl"])
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        found = await registry.detail("wheat-flour")
        assert found is not None
        assert found.names[GERMAN].count("Mehl") == 1


class TestSafety:
    async def test_an_eaters_constraint_follows_the_merge(self) -> None:
        """The one no foreign key protects. `eater_constraint.ingredient_slug` is text, so
        an eater avoiding `plain-flour` would silently stop being warned the moment that
        entry merged away — an allergy that stops firing and says nothing."""
        await two_entries()
        async with session() as active:
            cook = CookRow(
                email="cook@example.com",
                display_name="Cook",
                password_hash="x",
                standing=Standing.APPROVED,
            )
            active.add(cook)
            await active.flush()
            assert cook.id is not None
            eater = EaterRow(cook_id=cook.id, name="Ada", age_band=AgeBand.ADULT)
            active.add(eater)
            await active.flush()
            assert eater.id is not None
            active.add(
                EaterConstraintRow(
                    eater_id=eater.id, ingredient_slug="plain-flour", severity=Severity.MEDICAL
                )
            )
            await active.commit()

        await registry.merge(keeper="wheat-flour", loser="plain-flour")

        async with session() as active:
            held = (await active.exec(select(EaterConstraintRow))).all()
        assert [row.ingredient_slug for row in held] == ["wheat-flour"]

    async def test_allergens_are_the_union_of_both(self) -> None:
        """Merging can add an allergen and must never remove one: two entries that
        disagree are two examinations of one food, and the cautious reading is the only
        safe one (ADR-006)."""
        await two_entries()
        await registry.classify("plain-flour", frozenset({Allergen.SOYBEANS}))
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        found = await registry.detail("wheat-flour")
        assert found is not None
        assert found.entry.allergens == frozenset({Allergen.GLUTEN, Allergen.SOYBEANS})

    async def test_an_examination_on_either_side_counts_as_one(self) -> None:
        """The keeper was examined and the loser was not. They are the same food, so the
        examination still stands."""
        await two_entries()
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        found = await registry.detail("wheat-flour")
        assert found is not None
        assert found.entry.classified is True

    async def test_an_unexamined_keeper_gains_the_losers_examination(self) -> None:
        await registry.register(
            slug="a", kind=IngredientKind.SOLID, density=None, names={ENGLISH: ["a"]}
        )
        await registry.register(
            slug="b",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["b"]},
            allergens=frozenset({Allergen.MILK}),
        )
        await registry.merge(keeper="a", loser="b")
        found = await registry.detail("a")
        assert found is not None
        assert found.entry.classified is True
        assert found.entry.allergens == frozenset({Allergen.MILK})

    async def test_neither_examined_stays_unexamined(self) -> None:
        await registry.register(
            slug="a", kind=IngredientKind.SOLID, density=None, names={ENGLISH: ["a"]}
        )
        await registry.register(
            slug="b", kind=IngredientKind.SOLID, density=None, names={ENGLISH: ["b"]}
        )
        await registry.merge(keeper="a", loser="b")
        found = await registry.detail("a")
        assert found is not None
        assert found.entry.classified is False


class TestFacts:
    async def test_a_gap_in_the_keeper_is_filled_from_the_loser(self) -> None:
        """They are the same food, so a figure on either side describes it."""
        await registry.register(
            slug="a", kind=IngredientKind.SOLID, density=None, names={ENGLISH: ["a"]}
        )
        await registry.register(
            slug="b",
            kind=IngredientKind.SOLID,
            density=Decimal("0.5"),
            names={ENGLISH: ["b"]},
        )
        await registry.merge(keeper="a", loser="b")
        found = await registry.detail("a")
        assert found is not None
        assert found.entry.density == Decimal("0.5000")

    async def test_the_keepers_own_figure_wins(self) -> None:
        """An admin merging *into* this entry has chosen it as the truthful one."""
        await two_entries()
        await registry.amend("plain-flour", density=Decimal("0.9"))
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        found = await registry.detail("wheat-flour")
        assert found is not None
        assert found.entry.density == Decimal("0.5930")

    async def test_the_keepers_kind_is_kept(self) -> None:
        await two_entries()
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        found = await registry.detail("wheat-flour")
        assert found is not None
        assert found.entry.kind is IngredientKind.POWDER

    async def test_nutrition_from_the_loser_comes_across(self) -> None:
        keeper_id, loser_id = await two_entries()
        await registry.record_profile(
            NutrientProfile(
                ingredient_id=loser_id,
                source=NutritionSource.SWISS,
                reference="plain flour",
                amounts={Nutrient.ENERGY_KCAL: Decimal("364")},
            )
        )
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        profiles = await registry.profiles_for([keeper_id])
        assert [profile.amounts[Nutrient.ENERGY_KCAL] for profile in profiles] == [
            Decimal("364.000")
        ]

    async def test_a_figure_both_sides_publish_is_not_duplicated(self) -> None:
        """`(ingredient_id, source, nutrient)` is unique, so repointing would fail."""
        keeper_id, loser_id = await two_entries()
        for ingredient_id, value, reference in (
            (keeper_id, "364", "wheat flour"),
            (loser_id, "999", "plain flour"),
        ):
            await registry.record_profile(
                NutrientProfile(
                    ingredient_id=ingredient_id,
                    source=NutritionSource.SWISS,
                    reference=reference,
                    amounts={Nutrient.ENERGY_KCAL: Decimal(value)},
                )
            )
        await registry.merge(keeper="wheat-flour", loser="plain-flour")
        profiles = await registry.profiles_for([keeper_id])
        # The keeper's own figure stands: it is the entry the admin chose to keep.
        assert [profile.amounts[Nutrient.ENERGY_KCAL] for profile in profiles] == [
            Decimal("364.000")
        ]


class TestRefusals:
    async def test_merging_an_entry_into_itself_is_refused(self) -> None:
        await two_entries()
        with pytest.raises(NothingToMerge):
            await registry.merge(keeper="wheat-flour", loser="wheat-flour")

    async def test_an_unknown_keeper_is_refused(self) -> None:
        await two_entries()
        with pytest.raises(IngredientNotRegistered):
            await registry.merge(keeper="no-such-thing", loser="plain-flour")

    async def test_an_unknown_loser_is_refused(self) -> None:
        await two_entries()
        with pytest.raises(IngredientNotRegistered):
            await registry.merge(keeper="wheat-flour", loser="no-such-thing")

    async def test_a_refused_merge_changes_nothing(self) -> None:
        await two_entries()
        with pytest.raises(IngredientNotRegistered):
            await registry.merge(keeper="wheat-flour", loser="no-such-thing")
        assert await registry.detail("plain-flour") is not None


class TestAnAcademyPageAboutTheLoser:
    """The ninth relationship (ADR-061).

    ADR-052 was written about eight, and the list keeps growing. This one is a real
    foreign key, so forgetting it fails loudly rather than silently — but a page about a
    food that no longer exists is still a page about nothing, and the point of writing
    each addition down is that somebody has to remember.
    """

    async def a_page_about(self, ingredient_id: int, slug: str) -> None:
        await academy.write(
            NewPage(
                slug=slug,
                kind=PageKind.INGREDIENT,
                wordings={
                    ENGLISH: Wording(
                        name="plain flour",
                        spellings=[],
                        summary="The everyday one.",
                        explanation="Around ten per cent protein.",
                    )
                },
            ),
            cook_id=await a_cook(),
            ingredient_id=ingredient_id,
        )

    async def test_the_page_survives_the_merge(self) -> None:
        _, loser = await two_entries()
        await self.a_page_about(loser, "about-plain-flour")

        await registry.merge(keeper="wheat-flour", loser="plain-flour")

        page = await academy.detail("about-plain-flour", ENGLISH)
        assert page is not None
        assert page.summary == "The everyday one."

    async def test_it_now_names_the_entry_that_survived(self) -> None:
        keeper, loser = await two_entries()
        await self.a_page_about(loser, "about-plain-flour")

        await registry.merge(keeper="wheat-flour", loser="plain-flour")

        assert await academy.entry_of("about-plain-flour") == keeper

    async def test_two_pages_about_one_food_are_not_a_conflict(self) -> None:
        """Nothing computes on which page is the page, so a second one is a hatnote
        rather than something to resolve (ADR-058)."""
        keeper, loser = await two_entries()
        await self.a_page_about(keeper, "about-wheat-flour")
        await self.a_page_about(loser, "about-plain-flour")

        await registry.merge(keeper="wheat-flour", loser="plain-flour")

        assert await academy.entry_of("about-wheat-flour") == keeper
        assert await academy.entry_of("about-plain-flour") == keeper
