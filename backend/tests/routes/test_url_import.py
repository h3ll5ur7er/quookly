"""Importing a recipe from a URL (UC-1.3) — the founding use case.

A cook pastes a link to a recipe buried in a thousand words of preamble and gets back
structured food. These tests stub the fetch and the model, because what is being checked
is the *sequence*: what gets resolved against the registry, what gets reported, and what
happens when a step of it fails.

Two rules from the requirements decide most of the behaviour below. An ingredient is
resolved against the registry, never against what a model said. And a failure is reported
rather than silently corrected (FR-9) — including the failures that are nobody's fault,
like a site that will not serve an automated reader.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access import model as inference
from quookly.access import web
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.errors import ContentRefused, ContentUnreachable, InferenceNotConfigured
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.contracts.web import ReadableContent
from quookly.engines import translation
from quookly.managers import seed
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

ENGLISH = "en-GB"
IMPORT = "/api/v1/recipes/import-url"
RECIPES = "/api/v1/recipes"
PAGE = "https://example.com/pancakes"

RECIPE_BLOCK = {
    "@type": "Recipe",
    "name": "Classic pancakes",
    "description": "A foolproof batter.",
    "recipeYield": "Makes 8 pancakes",
    "recipeIngredient": [
        "100g plain flour",
        "1 large egg",
        "300ml whole milk",
        "oil, for frying",
    ],
    "recipeInstructions": ["Sift the flour.", "Whisk in the egg and milk."],
}


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-test-signing-key-of-sufficient-length-01")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
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


@pytest.fixture
async def larder() -> dict[str, int]:
    """A registry that knows flour, eggs and milk — and has never heard of oil."""
    entries = {}
    for slug, name, kind, density, allergens in [
        ("plain-flour", "plain flour", IngredientKind.POWDER, Decimal("0.53"), {Allergen.GLUTEN}),
        ("egg", "egg", IngredientKind.COUNTABLE, None, {Allergen.EGGS}),
        ("whole-milk", "whole milk", IngredientKind.LIQUID, Decimal("1.03"), {Allergen.MILK}),
    ]:
        created = await registry.register(
            slug=slug,
            kind=kind,
            density=density,
            names={ENGLISH: [name]},
            origin=Origin.SEED,
            allergens=frozenset(allergens),
        )
        entries[slug] = created.id
    return entries


_NOT_GIVEN: list[dict[str, Any]] = [RECIPE_BLOCK]


#: What a model says when asked to name a food. `None` is an instance with none, which is
#: the ordinary self-hosted case and must not cost anybody an import.
_NAMED = {"Bergkäse": "mountain cheese"}


def serving(
    monkeypatch: MonkeyPatch,
    *,
    structured: list[dict[str, Any]] = _NOT_GIVEN,
    text: str = "some readable prose",
    language: str | None = None,
    naming: dict[str, str] | None = _NAMED,
) -> None:
    """Answer the fetch with this page. An empty `structured` means a page with no
    metadata at all, which is the blog case — so it must not fall back to the default.

    `naming` answers the model when the import names a new entry in this instance's other
    languages; `None` is an instance without one."""

    async def fetched(url: str) -> ReadableContent:
        return ReadableContent(
            url=url, text=text, title="A page", structured=structured, language=language
        )

    monkeypatch.setattr(web, "fetch_readable", fetched)

    async def named(name: str, source: str, wanted: str) -> str:
        if naming is None:
            raise InferenceNotConfigured("no model here")
        return naming.get(name, name)

    monkeypatch.setattr(translation, "name_of", named)


def failing(monkeypatch: MonkeyPatch, failure: Exception) -> None:
    async def refuse(url: str) -> ReadableContent:
        raise failure

    monkeypatch.setattr(web, "fetch_readable", refuse)


class TestTheHappyPath:
    async def test_a_recipe_comes_back(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        serving(monkeypatch)
        response = await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        assert response.status_code == 201, response.text
        assert response.json()["recipe"]["title"] == "Classic pancakes"

    async def test_it_is_stored_and_listed(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        serving(monkeypatch)
        await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        listed = (await client.get(RECIPES, headers=cook)).json()
        assert [recipe["title"] for recipe in listed] == ["Classic pancakes"]

    async def test_the_quantities_survive(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        serving(monkeypatch)
        recipe = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()["recipe"]
        flour = next(line for line in recipe["lines"] if line["ingredient"] == "plain flour")
        assert flour["quantity"]["display"] == "100 g"

    async def test_a_line_with_no_quantity_survives_as_one(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        serving(monkeypatch)
        recipe = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()["recipe"]
        oil = next(line for line in recipe["lines"] if line["ingredient"] == "oil")
        assert oil["quantity"] is None
        assert oil["preparation"] == "for frying"

    async def test_the_method_survives_in_order(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        serving(monkeypatch)
        recipe = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()["recipe"]
        assert [step["instruction"] for step in recipe["steps"]] == [
            "Sift the flour.",
            "Whisk in the egg and milk.",
        ]

    async def test_it_records_where_it_came_from(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Provenance is V1: a recipe read off a page is not a recipe somebody wrote."""
        serving(monkeypatch)
        recipe = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()["recipe"]
        assert recipe["provenance"] == "imported_url"

    async def test_it_says_how_the_page_was_read(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """A recipe that came out wrong is a different investigation depending on whether
        the page lied in its metadata or a model misread its prose."""
        serving(monkeypatch)
        outcome = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()
        assert outcome["read_from"] == "metadata"


class TestResolvingAgainstTheRegistry:
    async def test_a_known_ingredient_is_matched_rather_than_recreated(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """The registry is the authority. Matching is what makes a recipe's allergens
        knowable at all — the model's opinion of them is never consulted (ADR-006)."""
        serving(monkeypatch)
        await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        found = (
            await client.get("/api/v1/ingredients", params={"search": "plain flour"}, headers=cook)
        ).json()
        assert len([entry for entry in found if entry["slug"] == "plain-flour"]) == 1

    async def test_an_unknown_ingredient_is_recorded_and_reported(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Refusing the whole import over one unknown word would make the feature useless.
        Adding it silently would leave a cook unaware that something needs checking."""
        serving(monkeypatch)
        outcome = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()
        assert outcome["ingredients_added"] == ["oil"]

    async def test_a_new_ingredient_is_unexamined_rather_than_assumed_safe(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Nobody has looked at it, so nothing is known about its allergens. Recording it
        as clear would be the exact lie ADR-006 exists to prevent."""
        serving(monkeypatch)
        await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        await client.post(
            "/api/v1/eaters",
            json={
                "name": "Mira",
                "age_band": "child",
                "constraints": [
                    {"allergen": "peanuts", "ingredient_slug": None, "severity": "medical"}
                ],
            },
            headers=cook,
        )
        listed = (await client.get(RECIPES, headers=cook)).json()
        assert listed[0]["suitability"] == "unknown"

    async def test_a_name_with_shopping_words_still_finds_the_registry_entry(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """The registry holds "egg". A page asking for "3 large free-range eggs" must
        reach it — a second, unclassified entry would stop an egg allergy firing."""
        serving(
            monkeypatch,
            structured=[{**RECIPE_BLOCK, "recipeIngredient": ["3 large free-range eggs"]}],
        )
        outcome = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()
        assert outcome["ingredients_added"] == []
        assert outcome["recipe"]["lines"][0]["ingredient"] == "egg"

    async def test_nothing_new_is_reported_when_the_registry_knew_everything(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        serving(
            monkeypatch, structured=[{**RECIPE_BLOCK, "recipeIngredient": ["100g plain flour"]}]
        )
        outcome = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()
        assert outcome["ingredients_added"] == []


class TestAPageInAnotherLanguage:
    """A Swiss cook pasting a link to a Swiss site is the ordinary case (FR-10)."""

    async def test_a_german_ingredient_reaches_the_registry(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """Asked in English, "Mehl" resolves to nothing and becomes a new entry nobody has
        classified — and the recipe loses the gluten the registry knew about."""
        await seed.stock_registry()
        serving(
            monkeypatch,
            language="de",
            structured=[
                {
                    **RECIPE_BLOCK,
                    "name": "Pfannkuchen",
                    "recipeYield": "4 Portionen",
                    "recipeIngredient": ["150 g Mehl", "2,5 dl Milch", "3 Eier"],
                }
            ],
        )
        outcome = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()
        assert outcome["ingredients_added"] == []

    async def test_an_entry_it_invents_is_named_in_the_languages_this_instance_ships(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """An import creates an entry for a line that resolved to nothing, named in the
        language of the page and no other — so every other reader on the instance saw a
        word they could not read (ADR-029, Phase 8b).

        Named here rather than lazily on read, unlike a recipe's prose: it is a handful of
        short round trips at a known moment, and the alternative is a model call threaded
        through five different screens that each need a name.
        """
        await seed.stock_registry()
        serving(
            monkeypatch,
            language="de",
            structured=[
                {
                    **RECIPE_BLOCK,
                    "name": "Rösti",
                    "recipeYield": "4 Portionen",
                    "recipeIngredient": ["500 g Bergkäse"],
                }
            ],
        )

        outcome = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()
        assert outcome["ingredients_added"] == ["Bergkäse"]

        # An English cook on the same instance gets a word, not the German and not a slug.
        listed = (await client.get("/api/v1/registry?search=mountain", headers=cook)).json()
        assert [one["name"] for one in listed["entries"]] == ["mountain cheese"]

    async def test_an_instance_with_no_model_keeps_the_one_name_it_has(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """Naming is a convenience and the import is not. A model that cannot be reached
        must not cost a cook the recipe they pasted a link to."""
        await seed.stock_registry()
        serving(
            monkeypatch,
            language="de",
            naming=None,
            structured=[
                {
                    **RECIPE_BLOCK,
                    "name": "Rösti",
                    "recipeYield": "4 Portionen",
                    "recipeIngredient": ["500 g Bergkäse"],
                }
            ],
        )

        outcome = await client.post(IMPORT, json={"url": PAGE}, headers=cook)

        assert outcome.status_code == 201, outcome.text
        assert outcome.json()["ingredients_added"] == ["Bergkäse"]

    async def test_the_allergens_survive_the_translation(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """The point of the whole exercise. A recipe of Mehl, Milch and Eier is not an
        unknown quantity — it is flour, milk and eggs, and the registry has classified all
        three."""
        await seed.stock_registry()
        serving(
            monkeypatch,
            language="de",
            structured=[
                {
                    **RECIPE_BLOCK,
                    "recipeYield": "4 Portionen",
                    "recipeIngredient": ["150 g Mehl", "2,5 dl Milch", "3 Eier"],
                }
            ],
        )
        await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        await client.post(
            "/api/v1/eaters",
            json={
                "name": "Mira",
                "age_band": "child",
                "constraints": [
                    {"allergen": "gluten", "ingredient_slug": None, "severity": "medical"}
                ],
            },
            headers=cook,
        )
        listed = (await client.get(RECIPES, headers=cook)).json()
        assert listed[0]["suitability"] == "unsuitable"

    async def test_a_page_that_does_not_say_falls_back_to_the_cooks_language(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """Somebody who reads Quookly in German is likely importing German recipes, even
        from a page whose markup forgot to say so."""
        await seed.stock_registry()
        await client.put("/api/v1/setup/locale", json={"locale": "de-CH"}, headers=cook)
        serving(
            monkeypatch,
            language=None,
            structured=[
                {
                    **RECIPE_BLOCK,
                    "recipeYield": "4 Portionen",
                    "recipeIngredient": ["150 g Mehl"],
                }
            ],
        )
        outcome = (await client.post(IMPORT, json={"url": PAGE}, headers=cook)).json()
        assert outcome["ingredients_added"] == []


class TestWhenThePageWillNotCooperate:
    async def test_a_site_that_blocks_readers_says_so(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """The page works in the cook's own browser. Telling them that is more use than
        reporting a failure they cannot reproduce."""
        failing(monkeypatch, ContentRefused("403"))
        response = await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        assert response.status_code == 422
        assert "browser" in response.json()["detail"].lower()

    async def test_an_unreachable_page_says_so(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        failing(monkeypatch, ContentUnreachable("404"))
        response = await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        assert response.status_code == 422

    async def test_a_page_with_no_recipe_in_it_says_so(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """Half a recipe would look complete on the screen. FR-9: report, never correct."""
        serving(monkeypatch, structured=[])

        async def unconfigured(*args: Any, **options: Any) -> Any:
            raise InferenceNotConfigured("no provider")

        monkeypatch.setattr(inference, "complete_structured", unconfigured)
        response = await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        assert response.status_code == 422
        assert "model" in response.json()["detail"].lower()

    async def test_a_recipe_whose_yield_cannot_be_read_is_refused(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """A guessed yield misscales every quantity in the recipe, silently. Refusing is
        the honest answer until a recipe can record that it does not know."""
        serving(monkeypatch, structured=[{**RECIPE_BLOCK, "recipeYield": "a generous amount"}])
        response = await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        assert response.status_code == 422
        assert "how much" in response.json()["detail"].lower()

    async def test_nothing_is_stored_when_an_import_is_refused(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        larder: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        serving(monkeypatch, structured=[{**RECIPE_BLOCK, "recipeYield": "a generous amount"}])
        await client.post(IMPORT, json={"url": PAGE}, headers=cook)
        assert (await client.get(RECIPES, headers=cook)).json() == []


class TestWhatIsRefusedOutright:
    async def test_it_needs_an_account(self, client: AsyncClient) -> None:
        assert (await client.post(IMPORT, json={"url": PAGE})).status_code == 401

    @pytest.mark.parametrize("url", ["", "not a url", "javascript:alert(1)"])
    async def test_something_that_is_not_a_web_address(
        self, client: AsyncClient, cook: dict[str, str], url: str
    ) -> None:
        assert (await client.post(IMPORT, json={"url": url}, headers=cook)).status_code == 422
