"""A cook reads recipes in their own language (FR-10, V14).

The registry is defined in English and named in every language Quookly ships, and
`RecipeAccess` has always resolved names for whatever locale it was asked for. The routes
simply never asked for anything but English — so a Swiss cook reading a Swiss recipe saw
"plain flour" where the page had said "Mehl", and the machinery to do better was already
built and idle.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.managers import seed
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

RECIPES = "/api/v1/recipes"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-test-signing-key-of-sufficient-length-01")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    await seed.stock_registry()
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def cook(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "chef@example.com")


async def a_recipe(client: AsyncClient, cook: dict[str, str]) -> dict[str, Any]:
    found = (
        await client.get("/api/v1/ingredients", params={"search": "plain flour"}, headers=cook)
    ).json()
    return {
        "title": "Test",
        "yield_magnitude": "4",
        "yield_unit": "serving",
        "lines": [{"ingredient_id": found[0]["id"], "magnitude": "100", "unit": "g"}],
        "steps": [{"instruction": "Mix."}],
    }


async def speaking(client: AsyncClient, cook: dict[str, str], locale: str) -> None:
    response = await client.put("/api/v1/setup/locale", json={"locale": locale}, headers=cook)
    assert response.status_code == 200, response.text


class TestTheCooksOwnLanguage:
    async def test_a_german_cook_reads_german_ingredient_names(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        created = await client.post(RECIPES, json=await a_recipe(client, cook), headers=cook)
        await speaking(client, cook, "de-CH")
        detail = (await client.get(f"{RECIPES}/{created.json()['id']}", headers=cook)).json()
        assert detail["lines"][0]["ingredient"] == "Weissmehl"

    async def test_a_french_cook_reads_french_ingredient_names(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        created = await client.post(RECIPES, json=await a_recipe(client, cook), headers=cook)
        await speaking(client, cook, "fr-CH")
        detail = (await client.get(f"{RECIPES}/{created.json()['id']}", headers=cook)).json()
        assert detail["lines"][0]["ingredient"] == "farine"

    async def test_an_english_cook_is_unaffected(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        created = await client.post(RECIPES, json=await a_recipe(client, cook), headers=cook)
        await speaking(client, cook, "en-GB")
        detail = (await client.get(f"{RECIPES}/{created.json()['id']}", headers=cook)).json()
        assert detail["lines"][0]["ingredient"] == "plain flour"

    async def test_a_cook_who_has_chosen_nothing_reads_english(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """The language the registry is defined in, which is the one always answerable."""
        created = await client.post(RECIPES, json=await a_recipe(client, cook), headers=cook)
        detail = (await client.get(f"{RECIPES}/{created.json()['id']}", headers=cook)).json()
        assert detail["lines"][0]["ingredient"] == "plain flour"

    async def test_it_takes_effect_the_moment_the_language_changes(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """Nothing is stored per language, so nothing needs re-importing."""
        created = await client.post(RECIPES, json=await a_recipe(client, cook), headers=cook)
        recipe_id = created.json()["id"]
        for locale, expected in (
            ("de-CH", "Weissmehl"),
            ("fr-CH", "farine"),
            ("en-GB", "plain flour"),
        ):
            await speaking(client, cook, locale)
            detail = (await client.get(f"{RECIPES}/{recipe_id}", headers=cook)).json()
            assert detail["lines"][0]["ingredient"] == expected, locale

    async def test_cooks_do_not_read_each_others_language(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await speaking(client, cook, "de-CH")
        neighbour = await sign_up(client, "neighbour@example.com")
        theirs = neighbour
        created = await client.post(RECIPES, json=await a_recipe(client, theirs), headers=theirs)
        detail = (await client.get(f"{RECIPES}/{created.json()['id']}", headers=theirs)).json()
        assert detail["lines"][0]["ingredient"] == "plain flour"


class TestFindingAnIngredient:
    async def test_a_german_cook_searches_in_german(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """This is the box on the household screen where an allergy is recorded. A cook
        who types "Mehl" and finds nothing records no constraint at all."""
        await speaking(client, cook, "de-CH")
        found = (
            await client.get("/api/v1/ingredients", params={"search": "Mehl"}, headers=cook)
        ).json()
        assert any(entry["slug"] == "plain-flour" for entry in found), found

    async def test_the_results_are_named_in_their_language(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await speaking(client, cook, "de-CH")
        found = (
            await client.get("/api/v1/ingredients", params={"search": "Mehl"}, headers=cook)
        ).json()
        flour = next(entry for entry in found if entry["slug"] == "plain-flour")
        assert flour["name"] == "Weissmehl"

    async def test_english_still_finds_english(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        found = (
            await client.get("/api/v1/ingredients", params={"search": "flour"}, headers=cook)
        ).json()
        assert any(entry["slug"] == "plain-flour" for entry in found)


class TestExportStaysEnglish:
    async def test_a_document_carries_the_language_every_instance_shares(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """The format carries one locale's names, and English is the one the registry is
        defined in — so an English export is the one that resolves everywhere. Exporting a
        cook's own language would make a document readable on fewer instances, not more."""
        await client.post(RECIPES, json=await a_recipe(client, cook), headers=cook)
        await speaking(client, cook, "de-CH")
        document = (await client.get(f"{RECIPES}/export", headers=cook)).json()
        assert document["locale"] == "en-GB"
        assert document["ingredients"][0]["names"][0] == "plain flour"
