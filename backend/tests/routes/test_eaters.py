"""Eaters through the API (UC-6.3, UC-6.4, UC-6.5).

This is where a cook first types in an allergy, so the tests here are mostly about the
two ways that goes wrong: somebody else's household leaking in, and an edit that does not
remove what the cook removed.
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


@pytest.fixture
async def neighbour(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "neighbour@example.com")


def eater(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "Mira",
        "age_band": "child",
        "appetite": "0.6",
        "constraints": [],
        **overrides,
    }


PEANUT = {"allergen": "peanuts", "ingredient_slug": None, "severity": "medical"}
CORIANDER = {"allergen": None, "ingredient_slug": "coriander-leaf", "severity": "preference"}


class TestRecording:
    async def test_an_eater_is_created(self, client: AsyncClient, cook: dict[str, str]) -> None:
        response = await client.post(EATERS, json=eater(), headers=cook)
        assert response.status_code == 201
        assert response.json()["name"] == "Mira"

    async def test_the_household_lists(self, client: AsyncClient, cook: dict[str, str]) -> None:
        await client.post(EATERS, json=eater(name="Ana", age_band="adult"), headers=cook)
        await client.post(EATERS, json=eater(), headers=cook)
        listed = await client.get(EATERS, headers=cook)
        assert [person["name"] for person in listed.json()] == ["Ana", "Mira"]

    async def test_an_appetite_reads_back_as_written(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """A string, not a JSON number: these are summed, and browsers sum in floats."""
        response = await client.post(EATERS, json=eater(appetite="0.6"), headers=cook)
        assert response.json()["appetite"] == "0.6"

    async def test_appetite_may_be_left_out(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        body = eater()
        del body["appetite"]
        response = await client.post(EATERS, json=body, headers=cook)
        assert response.json()["appetite"] == "1"

    async def test_an_eater_can_be_fetched_alone(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        created = await client.post(EATERS, json=eater(), headers=cook)
        response = await client.get(f"{EATERS}/{created.json()['id']}", headers=cook)
        assert response.status_code == 200
        assert response.json()["age_band"] == "child"


class TestConstraints:
    async def test_a_constraint_is_recorded(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        response = await client.post(EATERS, json=eater(constraints=[PEANUT]), headers=cook)
        assert response.json()["constraints"] == [PEANUT]

    async def test_a_constraint_naming_nothing_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        empty = {"allergen": None, "ingredient_slug": None, "severity": "medical"}
        response = await client.post(EATERS, json=eater(constraints=[empty]), headers=cook)
        assert response.status_code == 422

    async def test_a_constraint_naming_both_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """Ambiguous about what is really being avoided, so it is not stored at all."""
        both = {"allergen": "peanuts", "ingredient_slug": "peanut", "severity": "medical"}
        response = await client.post(EATERS, json=eater(constraints=[both]), headers=cook)
        assert response.status_code == 422

    async def test_an_unknown_severity_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        odd = {"allergen": "peanuts", "ingredient_slug": None, "severity": "quite-bad"}
        response = await client.post(EATERS, json=eater(constraints=[odd]), headers=cook)
        assert response.status_code == 422


class TestEditing:
    async def test_a_change_replaces_what_was_there(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        created = await client.post(EATERS, json=eater(constraints=[PEANUT]), headers=cook)
        response = await client.put(
            f"{EATERS}/{created.json()['id']}",
            json=eater(name="Mira Meier", constraints=[CORIANDER]),
            headers=cook,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Mira Meier"
        assert response.json()["constraints"] == [CORIANDER]

    async def test_a_removed_constraint_is_gone_on_the_next_read(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """The one that matters. An allergy deleted in the interface must not come back."""
        created = await client.post(
            EATERS, json=eater(constraints=[PEANUT, CORIANDER]), headers=cook
        )
        eater_id = created.json()["id"]
        await client.put(f"{EATERS}/{eater_id}", json=eater(constraints=[]), headers=cook)
        response = await client.get(f"{EATERS}/{eater_id}", headers=cook)
        assert response.json()["constraints"] == []

    async def test_editing_somebody_who_is_not_there(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        response = await client.put(f"{EATERS}/404", json=eater(), headers=cook)
        assert response.status_code == 404


class TestRemoving:
    async def test_an_eater_can_be_removed(self, client: AsyncClient, cook: dict[str, str]) -> None:
        created = await client.post(EATERS, json=eater(), headers=cook)
        eater_id = created.json()["id"]
        assert (await client.delete(f"{EATERS}/{eater_id}", headers=cook)).status_code == 204
        assert (await client.get(f"{EATERS}/{eater_id}", headers=cook)).status_code == 404

    async def test_removing_somebody_who_is_not_there(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        assert (await client.delete(f"{EATERS}/404", headers=cook)).status_code == 404


class TestOtherHouseholds:
    async def test_a_household_is_not_listed_to_anybody_else(
        self, client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str]
    ) -> None:
        await client.post(EATERS, json=eater(constraints=[PEANUT]), headers=cook)
        assert (await client.get(EATERS, headers=neighbour)).json() == []

    async def test_somebody_elses_eater_is_not_readable(
        self, client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str]
    ) -> None:
        """A 404 rather than a 403: whether that id exists is not their business either."""
        created = await client.post(EATERS, json=eater(constraints=[PEANUT]), headers=cook)
        response = await client.get(f"{EATERS}/{created.json()['id']}", headers=neighbour)
        assert response.status_code == 404

    async def test_somebody_elses_eater_is_not_editable(
        self, client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str]
    ) -> None:
        created = await client.post(EATERS, json=eater(constraints=[PEANUT]), headers=cook)
        response = await client.put(
            f"{EATERS}/{created.json()['id']}", json=eater(), headers=neighbour
        )
        assert response.status_code == 404

    async def test_somebody_elses_eater_is_not_removable(
        self, client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str]
    ) -> None:
        created = await client.post(EATERS, json=eater(), headers=cook)
        response = await client.delete(f"{EATERS}/{created.json()['id']}", headers=neighbour)
        assert response.status_code == 404
        assert len((await client.get(EATERS, headers=cook)).json()) == 1


class TestWithoutSigningIn:
    async def test_listing_needs_an_account(self, client: AsyncClient) -> None:
        assert (await client.get(EATERS)).status_code == 401

    async def test_creating_needs_an_account(self, client: AsyncClient) -> None:
        assert (await client.post(EATERS, json=eater())).status_code == 401


class TestWhatIsRefused:
    async def test_an_eater_with_no_name(self, client: AsyncClient, cook: dict[str, str]) -> None:
        response = await client.post(EATERS, json=eater(name=""), headers=cook)
        assert response.status_code == 422

    async def test_an_appetite_of_nothing(self, client: AsyncClient, cook: dict[str, str]) -> None:
        response = await client.post(EATERS, json=eater(appetite="0"), headers=cook)
        assert response.status_code == 422

    async def test_an_unknown_age_band(self, client: AsyncClient, cook: dict[str, str]) -> None:
        response = await client.post(EATERS, json=eater(age_band="teenager"), headers=cook)
        assert response.status_code == 422


class TestSummary:
    async def test_an_empty_household_needs_nothing(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        response = await client.get(f"{EATERS}/summary", headers=cook)
        assert response.status_code == 200
        assert response.json() == {"people": 0, "servings": "0"}

    async def test_the_servings_are_summed_not_counted(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """Four people where one eats half is 3.5 servings, not 4 (FR-18)."""
        for name, appetite in (("Ana", "1"), ("Jonas", "1"), ("Nonna", "1"), ("Mira", "0.5")):
            await client.post(
                EATERS, json=eater(name=name, age_band="adult", appetite=appetite), headers=cook
            )
        response = await client.get(f"{EATERS}/summary", headers=cook)
        assert response.json() == {"people": 4, "servings": "3.5"}

    async def test_the_sum_does_not_drift(self, client: AsyncClient, cook: dict[str, str]) -> None:
        """0.3 + 1.4 + 0.6 reads as 2.3, which it would not through a JSON number."""
        for name, appetite in (("Toddler", "0.3"), ("Teen", "1.4"), ("Nonna", "0.6")):
            await client.post(
                EATERS, json=eater(name=name, age_band="adult", appetite=appetite), headers=cook
            )
        assert (await client.get(f"{EATERS}/summary", headers=cook)).json()["servings"] == "2.3"

    async def test_another_household_is_not_counted(
        self, client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str]
    ) -> None:
        await client.post(EATERS, json=eater(), headers=cook)
        assert (await client.get(f"{EATERS}/summary", headers=neighbour)).json()["people"] == 0

    async def test_the_summary_needs_an_account(self, client: AsyncClient) -> None:
        assert (await client.get(f"{EATERS}/summary")).status_code == 401
