"""Asking for a recipe through the API (UC-1.4, UC-1.5).

The sequence, and one rule that matters more than the rest of it: a recipe written for
people who cannot eat it is **refused with its reasons and not stored**.

That is stricter than importing, deliberately. An imported recipe exists in the world
whatever it contains; hiding it would be the interface deciding something about an allergy
on a cook's behalf (ADR-010). A generated one was asked for on these people's behalf, so
producing something they cannot eat is a failure of the request.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access import model as inference
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.errors import InferenceNotConfigured
from quookly.contracts.inference import Completion
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

GENERATED = "/api/v1/recipes/generated"

ANSWER = {
    "title": "Spinach and Ricotta Pie",
    "summary": "A Tuesday pie.",
    "recipe_yield": "Serves 4",
    "serves": "",
    "ingredients": ["400 g spinach", "250 g ricotta", "2 eggs"],
    "steps": [{"instruction": "Wilt the spinach.", "attention": "hands_on"}],
}

WITH_PEANUTS = {
    **ANSWER,
    "title": "Peanut Noodles",
    "ingredients": ["400 g spinach", "100 g peanut butter"],
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
async def pantry() -> dict[str, int]:
    entries = {}
    for slug, name, allergens in [
        ("spinach", "spinach", frozenset()),
        ("ricotta", "ricotta", frozenset({Allergen.MILK})),
        ("egg", "egg", frozenset({Allergen.EGGS})),
        ("peanut-butter", "peanut butter", frozenset({Allergen.PEANUTS})),
    ]:
        created = await registry.register(
            slug=slug,
            kind=IngredientKind.SOLID,
            density=None,
            names={"en-GB": [name]},
            origin=Origin.SEED,
            allergens=allergens,
        )
        entries[slug] = created.id
    return entries


def answering(body: dict[str, Any], monkeypatch: MonkeyPatch) -> dict[str, Any]:
    """Stand in for the model, recording what it was asked."""
    asked: dict[str, Any] = {}

    async def complete_structured(
        prompt: str, schema: dict[str, Any], system: str | None = None, **asked_for: Any
    ) -> tuple[dict[str, Any], Completion]:
        # The editing pass asks a second question. Only the first is the recipe.
        asked.setdefault("prompt", prompt)
        return body, Completion(text=json.dumps(body), model="test")

    monkeypatch.setattr(inference, "complete_structured", complete_structured)
    return asked


async def an_eater(client: AsyncClient, cook: dict[str, str], allergen: str) -> None:
    await client.post(
        "/api/v1/eaters",
        json={
            "name": "Mira",
            "age_band": "adult",
            "constraints": [{"allergen": allergen, "severity": "medical"}],
        },
        headers=cook,
    )


class TestAsking:
    async def test_signing_in_is_required(self, client: AsyncClient) -> None:
        assert (await client.post(GENERATED, json={"description": "a pie"})).status_code == 401

    async def test_a_recipe_comes_back_and_is_kept(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        answering(ANSWER, monkeypatch)
        made = await client.post(GENERATED, json={"description": "a spinach pie"}, headers=cook)

        assert made.status_code == 201
        assert made.json()["title"] == "Spinach and Ricotta Pie"
        assert made.json()["provenance"] == "generated"

        listed = await client.get("/api/v1/recipes", headers=cook)
        assert [one["title"] for one in listed.json()] == ["Spinach and Ricotta Pie"]

    async def test_the_quantities_are_read_rather_than_taken_on_trust(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """The same reader that handles a page. "400 g spinach" is a quantity because a
        tested function said so, not because a model wrote it."""
        answering(ANSWER, monkeypatch)
        made = await client.post(GENERATED, json={"description": "a pie"}, headers=cook)

        spinach = made.json()["lines"][0]
        assert spinach["ingredient"] == "spinach"
        assert spinach["quantity"]["display"] == "400 g"

    async def test_what_the_cook_has_is_asked_about_by_name(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """UC-1.4. The cook picks from their pantry and the ask is in the registry's words,
        not in ids."""
        asked = answering(ANSWER, monkeypatch)
        await client.post(GENERATED, json={"ingredient_ids": [pantry["spinach"]]}, headers=cook)
        assert "spinach" in asked["prompt"]

    async def test_saying_nothing_at_all_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """ "Write me a recipe" with no constraints is a question with too many answers."""
        assert (await client.post(GENERATED, json={}, headers=cook)).status_code == 422


class TestTheTable:
    async def test_the_household_is_told_what_to_avoid(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """In the prompt, to improve the odds. It is not the guarantee."""
        await an_eater(client, cook, "peanuts")
        asked = answering(ANSWER, monkeypatch)
        await client.post(GENERATED, json={"description": "a pie"}, headers=cook)

        assert "must not contain: peanuts" in asked["prompt"]

    async def test_a_recipe_the_table_cannot_eat_is_refused(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """The guarantee. The model was told not to and did anyway; the verdict is taken
        from the resolved ingredients and it wins."""
        await an_eater(client, cook, "peanuts")
        answering(WITH_PEANUTS, monkeypatch)

        refused = await client.post(GENERATED, json={"description": "a pie"}, headers=cook)
        assert refused.status_code == 422

    async def test_a_refusal_says_who_and_what(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """ "No" without a reason is not an answer."""
        await an_eater(client, cook, "peanuts")
        answering(WITH_PEANUTS, monkeypatch)

        refused = await client.post(GENERATED, json={"description": "a pie"}, headers=cook)
        verdict = refused.json()["detail"]["verdict"]
        assert verdict["outcome"] == "unsuitable"
        assert [finding["eater"] for finding in verdict["findings"]] == ["Mira"]
        assert [finding["ingredient"] for finding in verdict["findings"]] == ["peanut butter"]

    async def test_a_refused_recipe_is_not_kept(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Unlike an imported one. This was asked for on these people's behalf, so it is a
        failure of the request rather than a fact about a recipe."""
        await an_eater(client, cook, "peanuts")
        answering(WITH_PEANUTS, monkeypatch)
        await client.post(GENERATED, json={"description": "a pie"}, headers=cook)

        assert (await client.get("/api/v1/recipes", headers=cook)).json() == []

    async def test_with_nobody_described_there_is_nothing_to_judge_against(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """An empty household satisfies every constraint there is. Refusing here would be
        a refusal about a question nobody asked."""
        answering(WITH_PEANUTS, monkeypatch)
        made = await client.post(GENERATED, json={"description": "a pie"}, headers=cook)
        assert made.status_code == 201


class TestWhenItCannotHelp:
    async def test_an_instance_with_no_model_says_so(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        async def refuse(*args: Any, **kwargs: Any) -> Any:
            raise InferenceNotConfigured("nothing configured")

        monkeypatch.setattr(inference, "complete_structured", refuse)
        refused = await client.post(GENERATED, json={"description": "a pie"}, headers=cook)

        assert refused.status_code == 422
        assert "none configured" in refused.json()["detail"]

    async def test_an_answer_with_nothing_in_it_says_so(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        answering({**ANSWER, "ingredients": []}, monkeypatch)
        refused = await client.post(GENERATED, json={"description": "a pie"}, headers=cook)

        assert refused.status_code == 422
        assert "Nothing usable" in refused.json()["detail"]

    async def test_an_answer_that_does_not_say_how_much_it_makes(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        answering({**ANSWER, "recipe_yield": ""}, monkeypatch)
        refused = await client.post(GENERATED, json={"description": "a pie"}, headers=cook)

        assert refused.status_code == 422
        assert "how much it makes" in refused.json()["detail"]


class TestMakingAVersionOfSomething:
    """UC-1.7. The same sequence as writing one outright, with the original in the asking
    and a record of where it came from."""

    async def an_original(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> int:
        created = await client.post(
            "/api/v1/recipes",
            json={
                "title": "Spinach Bake",
                "yield_magnitude": "4",
                "yield_unit": "serving",
                "lines": [
                    {"ingredient_id": pantry["spinach"], "magnitude": "400", "unit": "g"},
                    {"ingredient_id": pantry["ricotta"], "magnitude": "250", "unit": "g"},
                ],
                "steps": [{"instruction": "Bake it."}],
            },
            headers=cook,
        )
        return int(created.json()["id"])

    async def test_a_version_comes_back_and_is_kept(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        original = await self.an_original(client, cook, pantry)
        answering(ANSWER, monkeypatch)

        made = await client.post(
            f"/api/v1/recipes/{original}/variants",
            json={"change": "make it dairy-free"},
            headers=cook,
        )
        assert made.status_code == 201
        assert made.json()["provenance"] == "derived"

    async def test_it_records_what_it_came_from(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """A cook looking at a dairy-free shortbread should be one tap from the shortbread."""
        original = await self.an_original(client, cook, pantry)
        answering(ANSWER, monkeypatch)

        made = await client.post(
            f"/api/v1/recipes/{original}/variants",
            json={"change": "make it dairy-free"},
            headers=cook,
        )
        assert made.json()["derived_from"] == original
        assert made.json()["derived_from_title"] == "Spinach Bake"

    async def test_the_original_goes_into_the_asking(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """As words rather than as a data structure: a model adapts a recipe better when it
        is reading a recipe."""
        original = await self.an_original(client, cook, pantry)
        asked = answering(ANSWER, monkeypatch)

        await client.post(
            f"/api/v1/recipes/{original}/variants",
            json={"change": "make it dairy-free"},
            headers=cook,
        )
        assert "Spinach Bake" in asked["prompt"]
        assert "400 g spinach" in asked["prompt"]
        assert "Bake it." in asked["prompt"]
        assert "make it dairy-free" in asked["prompt"]

    async def test_a_version_the_table_cannot_eat_is_refused(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        pantry: dict[str, int],
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Asking for a dairy-free version and being handed one with cream in it is the
        case this rule exists for."""
        original = await self.an_original(client, cook, pantry)
        await an_eater(client, cook, "peanuts")
        answering(WITH_PEANUTS, monkeypatch)

        refused = await client.post(
            f"/api/v1/recipes/{original}/variants",
            json={"change": "make it nut-free"},
            headers=cook,
        )
        assert refused.status_code == 422
        assert refused.json()["detail"]["verdict"]["outcome"] == "unsuitable"

    async def test_another_cooks_recipe_cannot_be_adapted(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        original = await self.an_original(client, cook, pantry)
        signed_up = await sign_up(client, "neighbour@example.com")
        other = signed_up

        refused = await client.post(
            f"/api/v1/recipes/{original}/variants", json={"change": "vegan"}, headers=other
        )
        assert refused.status_code == 404

    async def test_a_recipe_that_is_not_there(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        refused = await client.post(
            "/api/v1/recipes/9999/variants", json={"change": "vegan"}, headers=cook
        )
        assert refused.status_code == 404

    async def test_saying_nothing_to_change_is_refused(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        original = await self.an_original(client, cook, pantry)
        refused = await client.post(
            f"/api/v1/recipes/{original}/variants", json={"change": ""}, headers=cook
        )
        assert refused.status_code == 422
