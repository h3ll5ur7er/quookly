"""Whether the people at the table can eat this, on the way to a screen (V5, ADR-006).

`SuitabilityEngine` decides; these tests are about what reaches a cook. Two properties
matter more than the rest, and both are about not overstating what is known: an
unclassified ingredient must not read as safe, and a household nobody has described must
not read as satisfied.
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

ENGLISH = "en-GB"
EATERS = "/api/v1/eaters"
RECIPES = "/api/v1/recipes"


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
    response = await client.post(
        "/api/v1/accounts",
        json={
            "email": "chef@example.com",
            "display_name": "Emanuel",
            "password": "a-sufficiently-long-password",
        },
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
async def larder() -> dict[str, int]:
    """Three entries: one classified as carrying peanuts, one clear, one never examined."""
    entries = {}
    for slug, name, kind, density, allergens in [
        (
            "peanut-butter",
            "peanut butter",
            IngredientKind.SOLID,
            Decimal("1.1"),
            {Allergen.PEANUTS},
        ),
        ("plain-flour", "plain flour", IngredientKind.POWDER, Decimal("0.53"), set()),
        ("mystery-paste", "mystery paste", IngredientKind.SOLID, Decimal("1.0"), None),
    ]:
        created = await registry.register(
            slug=slug,
            kind=kind,
            density=density,
            names={ENGLISH: [name]},
            origin=Origin.SEED,
            allergens=None if allergens is None else frozenset(allergens),
        )
        entries[slug] = created.id
    return entries


def recipe_of(
    *slugs: str, larder: dict[str, int], optional: set[str] | None = None
) -> dict[str, Any]:
    return {
        "title": "Something",
        "yield_magnitude": "4",
        "yield_unit": "serving",
        "lines": [
            {
                "ingredient_id": larder[slug],
                "magnitude": "100",
                "unit": "g",
                "optional": slug in (optional or set()),
            }
            for slug in slugs
        ],
        "steps": [{"instruction": "Combine."}],
    }


async def author(client: AsyncClient, cook: dict[str, str], body: dict[str, Any]) -> int:
    created = await client.post(RECIPES, json=body, headers=cook)
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


async def add_eater(
    client: AsyncClient, cook: dict[str, str], name: str, constraints: list[dict[str, Any]]
) -> None:
    response = await client.post(
        EATERS,
        json={"name": name, "age_band": "adult", "constraints": constraints},
        headers=cook,
    )
    assert response.status_code == 201, response.text


PEANUT_ALLERGY = {"allergen": "peanuts", "ingredient_slug": None, "severity": "medical"}
LACTOSE = {"allergen": "milk", "ingredient_slug": None, "severity": "intolerance"}
DISLIKES_FLOUR = {"allergen": None, "ingredient_slug": "plain-flour", "severity": "preference"}


async def verdict(client: AsyncClient, cook: dict[str, str], recipe_id: int) -> Any:
    response = await client.get(f"{RECIPES}/{recipe_id}", headers=cook)
    assert response.status_code == 200, response.text
    return response.json()["suitability"]


class TestNobodyToJudgeAgainst:
    async def test_an_empty_household_gets_no_verdict_at_all(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        """ "Suitable" for nobody is a reassurance about a question nobody asked."""
        recipe_id = await author(client, cook, recipe_of("peanut-butter", larder=larder))
        assert await verdict(client, cook, recipe_id) is None


class TestKnownViolations:
    async def test_a_medical_allergy_makes_a_recipe_unsuitable(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        await add_eater(client, cook, "Mira", [PEANUT_ALLERGY])
        recipe_id = await author(client, cook, recipe_of("peanut-butter", larder=larder))
        assert (await verdict(client, cook, recipe_id))["outcome"] == "unsuitable"

    async def test_the_verdict_names_who_and_what(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        """A refusal a cook cannot act on is barely better than no answer."""
        await add_eater(client, cook, "Mira", [PEANUT_ALLERGY])
        recipe_id = await author(client, cook, recipe_of("peanut-butter", larder=larder))
        finding = (await verdict(client, cook, recipe_id))["findings"][0]
        assert finding["eater"] == "Mira"
        assert finding["ingredient"] == "peanut butter"

    async def test_an_ingredient_avoided_by_name_is_caught(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        await add_eater(client, cook, "Jonas", [DISLIKES_FLOUR])
        recipe_id = await author(client, cook, recipe_of("plain-flour", larder=larder))
        answer = await verdict(client, cook, recipe_id)
        assert answer["outcome"] == "suitable"
        assert answer["findings"][0]["ingredient"] == "plain flour"

    async def test_an_optional_ingredient_is_reported_as_avoidable(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        """Leaving it out is a more useful thing to tell a cook than a refusal."""
        await add_eater(client, cook, "Mira", [PEANUT_ALLERGY])
        recipe_id = await author(
            client,
            cook,
            recipe_of("plain-flour", "peanut-butter", larder=larder, optional={"peanut-butter"}),
        )
        answer = await verdict(client, cook, recipe_id)
        assert answer["outcome"] == "suitable"
        assert answer["findings"][0]["avoidable"] is True


class TestWhatIsNotKnown:
    async def test_an_unexamined_ingredient_makes_the_answer_unknown(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        """Silence about a nut is not an absence of nuts."""
        await add_eater(client, cook, "Mira", [PEANUT_ALLERGY])
        recipe_id = await author(client, cook, recipe_of("mystery-paste", larder=larder))
        answer = await verdict(client, cook, recipe_id)
        assert answer["outcome"] == "unknown"
        assert answer["findings"][0]["unknown"] is True

    async def test_a_classified_clear_ingredient_is_suitable(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        """The distinction the registry exists to keep: examined-and-clear is not silence."""
        await add_eater(client, cook, "Mira", [PEANUT_ALLERGY])
        recipe_id = await author(client, cook, recipe_of("plain-flour", larder=larder))
        assert (await verdict(client, cook, recipe_id))["outcome"] == "suitable"

    async def test_something_definitely_wrong_outranks_something_merely_unknown(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        await add_eater(client, cook, "Mira", [PEANUT_ALLERGY])
        recipe_id = await author(
            client, cook, recipe_of("mystery-paste", "peanut-butter", larder=larder)
        )
        assert (await verdict(client, cook, recipe_id))["outcome"] == "unsuitable"


class TestSeveralEaters:
    async def test_everybody_at_the_table_is_checked(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        await add_eater(client, cook, "Mira", [PEANUT_ALLERGY])
        await add_eater(client, cook, "Jonas", [LACTOSE])
        recipe_id = await author(client, cook, recipe_of("peanut-butter", larder=larder))
        answer = await verdict(client, cook, recipe_id)
        assert answer["outcome"] == "unsuitable"
        assert {finding["eater"] for finding in answer["findings"]} == {"Mira"}

    async def test_another_cooks_household_is_not_consulted(
        self, client: AsyncClient, cook: dict[str, str], larder: dict[str, int]
    ) -> None:
        """A verdict built from somebody else's allergies is worse than none."""
        neighbour = await client.post(
            "/api/v1/accounts",
            json={
                "email": "neighbour@example.com",
                "display_name": "Someone",
                "password": "a-sufficiently-long-password",
            },
        )
        theirs = {"Authorization": f"Bearer {neighbour.json()['token']}"}
        await add_eater(client, theirs, "Stranger", [PEANUT_ALLERGY])
        recipe_id = await author(client, cook, recipe_of("peanut-butter", larder=larder))
        assert await verdict(client, cook, recipe_id) is None
