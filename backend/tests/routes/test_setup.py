"""Guided setup, through the API (UC-10.2, UC-10.3).

Progress is derived from the profile every time it is asked for (ADR-014), so these tests
mostly change the profile by other endpoints and check that setup notices.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

SETUP = "/api/v1/setup"
EATERS = "/api/v1/eaters"


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


async def progress(client: AsyncClient, cook: dict[str, str]) -> Any:
    response = await client.get(SETUP, headers=cook)
    assert response.status_code == 200, response.text
    return response.json()


def settled(body: Any) -> set[str]:
    return {status["step"] for status in body["steps"] if status["done"]}


class TestAFreshAccount:
    async def test_has_everything_still_to_do(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        assert settled(await progress(client, cook)) == set()

    async def test_is_asked_for_the_household_first(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        assert (await progress(client, cook))["next_step"] == "household"

    async def test_sees_the_whole_road_rather_than_one_door(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        body = await progress(client, cook)
        assert [status["step"] for status in body["steps"]] == [
            "household",
            "constraints",
            "units",
            "locale",
        ]

    async def test_needs_an_account(self, client: AsyncClient) -> None:
        assert (await client.get(SETUP)).status_code == 401


class TestSettledByDoingTheWork:
    async def test_recording_somebody_settles_the_household(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.post(EATERS, json={"name": "Mira", "age_band": "child"}, headers=cook)
        assert "household" in settled(await progress(client, cook))

    async def test_recording_a_constraint_settles_the_constraints_step(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.post(
            EATERS,
            json={
                "name": "Mira",
                "age_band": "child",
                "constraints": [
                    {"allergen": "peanuts", "ingredient_slug": None, "severity": "medical"}
                ],
            },
            headers=cook,
        )
        assert "constraints" in settled(await progress(client, cook))

    async def test_a_household_with_nobody_restricted_is_still_asked(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.post(EATERS, json={"name": "Mira", "age_band": "child"}, headers=cook)
        assert "constraints" not in settled(await progress(client, cook))

    async def test_removing_everybody_reopens_the_household(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """The reason nothing is stored: a flag would still say it was done."""
        created = await client.post(
            EATERS, json={"name": "Mira", "age_band": "child"}, headers=cook
        )
        await client.delete(f"{EATERS}/{created.json()['id']}", headers=cook)
        assert "household" not in settled(await progress(client, cook))


class TestDeclaringNone:
    async def test_a_step_can_be_answered_with_nothing(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        response = await client.post(f"{SETUP}/declarations/constraints", headers=cook)
        assert response.status_code == 200
        assert "constraints" in settled(response.json())

    async def test_it_says_the_answer_was_a_declaration(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        body = (await client.post(f"{SETUP}/declarations/constraints", headers=cook)).json()
        status = next(s for s in body["steps"] if s["step"] == "constraints")
        assert status["declared"] is True

    async def test_declaring_twice_is_not_an_error(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.post(f"{SETUP}/declarations/constraints", headers=cook)
        second = await client.post(f"{SETUP}/declarations/constraints", headers=cook)
        assert second.status_code == 200

    async def test_a_declaration_survives_the_profile_emptying(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """They were asked and they answered. Emptying the list does not unask it."""
        await client.post(f"{SETUP}/declarations/household", headers=cook)
        assert "household" in settled(await progress(client, cook))

    async def test_an_unknown_step_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        assert (await client.post(f"{SETUP}/declarations/pudding", headers=cook)).status_code == 422

    async def test_declarations_belong_to_one_cook(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.post(f"{SETUP}/declarations/constraints", headers=cook)
        neighbour = await sign_up(client, "neighbour@example.com")
        assert "constraints" not in settled(await progress(client, neighbour))


class TestLanguage:
    async def test_choosing_a_language_settles_the_step(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        response = await client.put(f"{SETUP}/locale", json={"locale": "de-CH"}, headers=cook)
        assert response.status_code == 200
        assert "locale" in settled(response.json())

    async def test_the_choice_is_remembered(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """So a cook signing in on a second device gets their own language, not the browser's."""
        await client.put(f"{SETUP}/locale", json={"locale": "fr-CH"}, headers=cook)
        assert (await client.get("/api/v1/accounts/me", headers=cook)).json()["locale"] == "fr-CH"

    async def test_a_language_the_instance_does_not_speak_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """Storing one would leave a cook with an interface in a language nobody wrote."""
        response = await client.put(f"{SETUP}/locale", json={"locale": "xx-XX"}, headers=cook)
        assert response.status_code == 422


class TestFinishing:
    async def test_setup_completes_when_nothing_is_outstanding(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.post(
            EATERS,
            json={
                "name": "Mira",
                "age_band": "child",
                "constraints": [
                    {"allergen": "peanuts", "ingredient_slug": None, "severity": "medical"}
                ],
            },
            headers=cook,
        )
        await client.post(f"{SETUP}/declarations/units", headers=cook)
        await client.put(f"{SETUP}/locale", json={"locale": "en-GB"}, headers=cook)
        body = await progress(client, cook)
        assert body["complete"] is True
        assert body["next_step"] is None
