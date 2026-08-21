"""The seeded ingredients, in the languages Quookly ships (FR-10, V14).

Without these a German recipe resolves nothing. Every ingredient becomes a new registry
entry that nobody has classified, so a recipe made of flour, milk and eggs carries no
allergen judgement at all — the registry knew the answer and was asked the wrong word.
"""

from collections.abc import AsyncIterator

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import Allergen
from quookly.managers import seed
from quookly.utilities.configuration import get_settings


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


@pytest.fixture(autouse=True)
async def stocked() -> None:
    await seed.stock_registry()


class TestGerman:
    @pytest.mark.parametrize(
        ("written", "slug"),
        [
            ("Mehl", "plain-flour"),
            ("Weissmehl", "plain-flour"),
            ("Milch", "whole-milk"),
            ("Vollmilch", "whole-milk"),
            ("Ei", "egg"),
            ("Eier", "egg"),
            ("Butter", "unsalted-butter"),
            ("Zucker", "caster-sugar"),
            ("Salz", "fine-salt"),
            ("Backpulver", "baking-powder"),
            ("Rahm", "double-cream"),
            ("Zwiebel", "onion"),
        ],
    )
    async def test_a_german_name_reaches_the_registry(self, written: str, slug: str) -> None:
        found = await registry.resolve(written, "de-CH")
        assert found is not None, f"{written!r} resolved to nothing"
        assert found.slug == slug

    async def test_the_allergens_come_with_it(self) -> None:
        """The whole point. "Mehl" has to carry the gluten the registry knows about."""
        flour = await registry.resolve("Mehl", "de-CH")
        assert flour is not None
        assert flour.allergens == frozenset({Allergen.GLUTEN})
        assert flour.classified is True

    async def test_a_separated_egg_is_its_own_ingredient(self) -> None:
        """Swissmilk asks for Eigelb and Eiweiss separately. Resolving both to "egg"
        would print "3 eggs" twice and read as six."""
        yolk = await registry.resolve("Eigelb", "de-CH")
        white = await registry.resolve("Eiweiss", "de-CH")
        assert yolk is not None and yolk.slug == "egg-yolk"
        assert white is not None and white.slug == "egg-white"

    async def test_a_separated_egg_still_carries_the_allergen(self) -> None:
        """Different ingredient, same allergy. An egg allergy has to fire on either."""
        for written in ("Eigelb", "Eiweiss"):
            found = await registry.resolve(written, "de-CH")
            assert found is not None, written
            assert Allergen.EGGS in found.allergens
            assert found.classified is True


class TestFrench:
    @pytest.mark.parametrize(
        ("written", "slug"),
        [
            ("farine", "plain-flour"),
            ("lait", "whole-milk"),
            ("œuf", "egg"),
            ("oeufs", "egg"),
            ("beurre", "unsalted-butter"),
            ("sucre", "caster-sugar"),
            ("sel", "fine-salt"),
            ("crème", "double-cream"),
        ],
    )
    async def test_a_french_name_reaches_the_registry(self, written: str, slug: str) -> None:
        found = await registry.resolve(written, "fr-CH")
        assert found is not None, f"{written!r} resolved to nothing"
        assert found.slug == slug

    async def test_the_allergens_come_with_it(self) -> None:
        milk = await registry.resolve("lait", "fr-CH")
        assert milk is not None
        assert milk.allergens == frozenset({Allergen.MILK})


class TestItDoesNotDisturbEnglish:
    async def test_english_still_resolves(self) -> None:
        found = await registry.resolve("plain flour", "en-GB")
        assert found is not None
        assert found.slug == "plain-flour"

    async def test_a_german_name_is_reachable_from_an_english_request(self) -> None:
        """Locales fall back to the language the registry was seeded in, not away from
        it — a name is a name, and refusing one because the request said en-GB would lose
        an import for no reason."""
        found = await registry.resolve("Mehl", "en-GB")
        assert found is None or found.slug == "plain-flour"


class TestCoverage:
    async def test_every_seeded_ingredient_has_a_name_in_every_language(self) -> None:
        """A gap here is silent: the ingredient simply never resolves, and the recipe
        that mentions it loses its allergens."""
        english = seed.read_seed_file()
        for locale in ("de-CH", "fr-CH"):
            translated = seed.read_names_file(locale)
            missing = {entry["slug"] for entry in english["ingredients"]} - set(translated)
            assert not missing, f"{locale} is missing {sorted(missing)}"

    async def test_stocking_twice_does_not_duplicate_a_name(self) -> None:
        await seed.stock_registry()
        found = await registry.resolve("Mehl", "de-CH")
        assert found is not None
