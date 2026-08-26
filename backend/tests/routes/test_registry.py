"""Reading the ingredient registry through the API (Phase 7).

The registry is the largest list in the app and, until this endpoint, the only part of
the system a cook could not look at. That matters because importing a recipe *creates*
entries: a line that resolves to nothing cannot be shopped for, scaled or judged, so
`RecipeManager` invents one. What it invents is a guess — `SOLID`, no density, allergens
deliberately unclassified because nobody has looked (ADR-006, ADR-029).

Nothing surfaced those guesses. These tests are about making them findable.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

REGISTRY = "/api/v1/registry"
ENGLISH = "en-GB"
GERMAN = "de-CH"


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
async def stocked() -> None:
    """Two entries somebody chose, and one an import invented."""
    await registry.register(
        slug="unsalted-butter",
        kind=IngredientKind.SOLID,
        density=Decimal("0.911"),
        names={ENGLISH: ["unsalted butter"], GERMAN: ["ungesalzene Butter"]},
        origin=Origin.SEED,
        allergens=frozenset({Allergen.MILK}),
    )
    await registry.register(
        slug="water",
        kind=IngredientKind.LIQUID,
        density=Decimal("1.0"),
        names={ENGLISH: ["water"], GERMAN: ["Wasser"]},
        origin=Origin.SEED,
        allergens=frozenset(),
    )
    await registry.register(
        slug="creme-fraiche",
        kind=IngredientKind.SOLID,
        density=None,
        names={ENGLISH: ["crème fraîche"]},
        origin=Origin.USER,
    )


def by_slug(body: Any) -> dict[str, Any]:
    return {entry["slug"]: entry for entry in body["entries"]}


class TestReading:
    async def test_the_registry_can_be_listed(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        response = await client.get(REGISTRY, headers=cook)
        assert response.status_code == 200
        assert set(by_slug(response.json())) == {"unsalted-butter", "water", "creme-fraiche"}

    async def test_the_total_says_how_much_there_is(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        body = (await client.get(REGISTRY, params={"limit": 1}, headers=cook)).json()
        assert len(body["entries"]) == 1
        assert body["total"] == 3

    async def test_an_entry_carries_what_is_needed_to_judge_it(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """Kind, density and origin — the three fields an import guesses at."""
        butter = by_slug((await client.get(REGISTRY, headers=cook)).json())["unsalted-butter"]
        assert butter["name"] == "unsalted butter"
        assert butter["kind"] == "solid"
        assert butter["density"] == "0.9110"
        assert butter["origin"] == "seed"

    async def test_signing_in_is_required(self, client: AsyncClient, stocked: None) -> None:
        assert (await client.get(REGISTRY)).status_code == 401


class TestFindingTheGuesses:
    async def test_unclassified_allergens_are_not_reported_as_none(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """The safety rule, at the edge of the API (ADR-006).

        Water carries no allergens and somebody said so. Crème fraîche carries none
        *recorded*, because nobody has looked — and it is milk. Both have an empty list,
        so the empty list cannot be what a client reads.
        """
        entries = by_slug((await client.get(REGISTRY, headers=cook)).json())
        assert entries["water"]["allergens"] == []
        assert entries["water"]["classified"] is True
        assert entries["creme-fraiche"]["allergens"] == []
        assert entries["creme-fraiche"]["classified"] is False

    async def test_what_an_import_invented_can_be_listed_on_its_own(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        body = (await client.get(REGISTRY, params={"origin": "user"}, headers=cook)).json()
        assert set(by_slug(body)) == {"creme-fraiche"}
        assert body["total"] == 1

    async def test_a_guess_shows_its_missing_density(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        entries = by_slug((await client.get(REGISTRY, headers=cook)).json())
        assert entries["creme-fraiche"]["density"] is None

    async def test_an_unknown_origin_is_refused_rather_than_ignored(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """Silently listing everything would answer a question nobody asked."""
        assert (
            await client.get(REGISTRY, params={"origin": "invented"}, headers=cook)
        ).status_code == 422


class TestSearching:
    async def test_a_term_narrows_the_list(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        body = (await client.get(REGISTRY, params={"search": "butter"}, headers=cook)).json()
        assert set(by_slug(body)) == {"unsalted-butter"}
        assert body["total"] == 1

    async def test_a_term_matching_nothing_is_an_empty_page(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        body = (await client.get(REGISTRY, params={"search": "saffron"}, headers=cook)).json()
        assert body["entries"] == []
        assert body["total"] == 0


class TestLanguage:
    async def test_entries_are_named_in_the_cooks_language(
        self, client: AsyncClient, stocked: None
    ) -> None:
        """A registry a Swiss cook reads in English is a registry they cannot correct."""
        swiss = await sign_up(client, "koch@example.com")
        await client.put("/api/v1/setup/locale", json={"locale": GERMAN}, headers=swiss)
        entries = by_slug((await client.get(REGISTRY, headers=swiss)).json())
        assert entries["water"]["name"] == "Wasser"

    async def test_an_entry_with_no_name_in_that_language_still_appears(
        self, client: AsyncClient, stocked: None
    ) -> None:
        """Falling back is what keeps browsing complete; hiding it would hide the guesses."""
        swiss = await sign_up(client, "koch@example.com")
        await client.put("/api/v1/setup/locale", json={"locale": GERMAN}, headers=swiss)
        entries = by_slug((await client.get(REGISTRY, headers=swiss)).json())
        assert entries["creme-fraiche"]["name"] == "crème fraîche"
