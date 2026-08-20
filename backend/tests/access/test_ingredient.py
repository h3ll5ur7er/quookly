"""The ingredient registry.

An ingredient line points at a registry entry rather than holding free text. That is what
makes quantities convertible, nutrition aggregable, allergens determinable and stock
matchable — none of which work against a string.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.errors import IngredientAlreadyRegistered
from quookly.contracts.ingredient import IngredientKind, Origin
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


async def register_butter() -> None:
    await registry.register(
        slug="unsalted-butter",
        kind=IngredientKind.SOLID,
        density=Decimal("0.911"),
        names={ENGLISH: ["unsalted butter", "sweet butter"], GERMAN: ["ungesalzene Butter"]},
        origin=Origin.SEED,
    )


class TestRegistering:
    async def test_a_registered_ingredient_can_be_resolved(self) -> None:
        await register_butter()
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.slug == "unsalted-butter"

    async def test_the_slug_is_the_identity_not_the_name(self) -> None:
        """Names are per locale; the slug is what a recipe actually points at."""
        await register_butter()
        english = await registry.resolve("unsalted butter", ENGLISH)
        german = await registry.resolve("ungesalzene Butter", GERMAN)
        assert english is not None and german is not None
        assert english.slug == german.slug
        assert english.id == german.id

    async def test_a_slug_may_only_be_registered_once(self) -> None:
        await register_butter()
        with pytest.raises(IngredientAlreadyRegistered):
            await register_butter()

    async def test_origin_is_recorded_so_upgrades_know_what_they_may_replace(self) -> None:
        """Seeded rows may be replaced by an upgrade; a cook's own may never be."""
        await register_butter()
        await registry.register(
            slug="grandmothers-spice-mix",
            kind=IngredientKind.POWDER,
            density=Decimal("0.5"),
            names={ENGLISH: ["grandmother's spice mix"]},
        )
        seeded = await registry.resolve("unsalted butter", ENGLISH)
        mine = await registry.resolve("grandmother's spice mix", ENGLISH)
        assert seeded is not None and mine is not None
        assert seeded.origin is Origin.SEED
        assert mine.origin is Origin.USER


class TestResolving:
    async def test_case_and_spacing_do_not_matter(self) -> None:
        """Someone typing into a form is not typing a database key."""
        await register_butter()
        for typed in ("Unsalted Butter", "  unsalted   butter ", "UNSALTED BUTTER"):
            assert await registry.resolve(typed, ENGLISH) is not None, typed

    async def test_an_alias_resolves_to_the_same_ingredient(self) -> None:
        """Recipes say cornflour or cornstarch and mean one thing."""
        await register_butter()
        alias = await registry.resolve("sweet butter", ENGLISH)
        canonical = await registry.resolve("unsalted butter", ENGLISH)
        assert alias is not None and canonical is not None
        assert alias.id == canonical.id

    async def test_the_canonical_name_comes_back_not_the_alias_typed(self) -> None:
        await register_butter()
        found = await registry.resolve("sweet butter", ENGLISH)
        assert found is not None
        assert found.name == "unsalted butter"

    async def test_the_name_is_resolved_for_the_requested_locale(self) -> None:
        await register_butter()
        found = await registry.resolve("ungesalzene Butter", GERMAN)
        assert found is not None
        assert found.name == "ungesalzene Butter"

    async def test_an_unknown_name_is_absent_not_an_error(self) -> None:
        """An unresolvable ingredient is reported to the cook, never invented (FR-9)."""
        assert await registry.resolve("moonstone", ENGLISH) is None

    async def test_a_seeded_english_name_still_resolves_on_a_swiss_instance(self) -> None:
        """The seed registry starts in English; a de-CH cook must still find it."""
        await registry.register(
            slug="caster-sugar",
            kind=IngredientKind.POWDER,
            density=Decimal("0.85"),
            names={ENGLISH: ["caster sugar"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("caster sugar", GERMAN)
        assert found is not None
        assert found.slug == "caster-sugar"

    async def test_a_locale_specific_name_wins_over_the_english_fallback(self) -> None:
        await registry.register(
            slug="cream",
            kind=IngredientKind.LIQUID,
            density=Decimal("0.994"),
            names={ENGLISH: ["cream"], GERMAN: ["Rahm"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("Rahm", GERMAN)
        assert found is not None
        assert found.name == "Rahm"


class TestDensity:
    async def test_density_is_available_for_conversion(self) -> None:
        """MeasureEngine takes density as an argument; this is where it comes from."""
        await register_butter()
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.density == Decimal("0.911")

    async def test_a_countable_ingredient_has_no_density(self) -> None:
        """An egg has a mass, but converting three eggs to millilitres is meaningless."""
        await registry.register(
            slug="egg",
            kind=IngredientKind.COUNTABLE,
            density=None,
            names={ENGLISH: ["egg"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("egg", ENGLISH)
        assert found is not None
        assert found.density is None

    async def test_densities_can_be_fetched_in_one_go(self) -> None:
        """A recipe needs every density at once; one query, not one per line."""
        await register_butter()
        await registry.register(
            slug="water",
            kind=IngredientKind.LIQUID,
            density=Decimal("1.0"),
            names={ENGLISH: ["water"]},
            origin=Origin.SEED,
        )
        butter = await registry.resolve("unsalted butter", ENGLISH)
        water = await registry.resolve("water", ENGLISH)
        assert butter is not None and water is not None

        densities = await registry.densities_for([butter.id, water.id])
        assert densities == {butter.id: Decimal("0.911"), water.id: Decimal("1.0")}


class TestKinds:
    async def test_the_kind_drives_which_unit_a_cook_prefers(self) -> None:
        """UC-6.2: powders in grams, liquids in millilitres — per kind, not globally."""
        await register_butter()
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.kind is IngredientKind.SOLID
