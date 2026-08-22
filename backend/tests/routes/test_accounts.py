"""The account endpoints, exercised through the API as a client would.

Routes are Client services: they resolve input, call one manager, and translate domain
errors into status codes. These tests pin the translation, since a domain error escaping
as a 500 is how an ordinary refusal becomes an incident.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.cook import Standing
from quookly.utilities.configuration import get_settings

APPLICATIONS = "/api/v1/accounts/applications"
PASSWORD = "a-sufficiently-long-password"
REGISTRATION: dict[str, Any] = {
    "email": "cook@example.com",
    "display_name": "Emanuel",
    "password": PASSWORD,
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


class TestBootstrap:
    async def test_a_fresh_instance_reports_that_it_needs_bootstrapping(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/accounts/bootstrap")
        assert response.status_code == 200
        assert response.json() == {"required": True}

    async def test_bootstrapping_creates_an_admin(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        assert response.status_code == 201
        body = response.json()
        assert body["cook"]["is_admin"] is True
        assert body["token"]

    async def test_the_bootstrap_closes_after_use(self, client: AsyncClient) -> None:
        await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        state = await client.get("/api/v1/accounts/bootstrap")
        assert state.json() == {"required": False}

    async def test_bootstrapping_twice_is_a_conflict_not_a_crash(self, client: AsyncClient) -> None:
        await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        second = await client.post(
            "/api/v1/accounts/bootstrap", json={**REGISTRATION, "email": "other@example.com"}
        )
        assert second.status_code == 409


class TestApplying:
    async def test_anybody_can_apply(self, client: AsyncClient) -> None:
        response = await client.post(APPLICATIONS, json=REGISTRATION)
        assert response.status_code == 201
        assert response.json()["is_admin"] is False
        assert response.json()["standing"] == "applied"

    async def test_no_token_comes_back(self, client: AsyncClient) -> None:
        """An application is not an account yet, and an endpoint that handed one over
        would be open registration wearing a different name."""
        response = await client.post(APPLICATIONS, json=REGISTRATION)
        assert "token" not in response.json()

    async def test_a_duplicate_email_is_a_conflict(self, client: AsyncClient) -> None:
        await client.post(APPLICATIONS, json=REGISTRATION)
        second = await client.post(APPLICATIONS, json=REGISTRATION)
        assert second.status_code == 409

    async def test_a_short_password_is_rejected_before_any_work(self, client: AsyncClient) -> None:
        response = await client.post(APPLICATIONS, json={**REGISTRATION, "password": "short"})
        assert response.status_code == 422

    async def test_a_malformed_email_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(APPLICATIONS, json={**REGISTRATION, "email": "nope"})
        assert response.status_code == 422

    async def test_the_password_never_comes_back(self, client: AsyncClient) -> None:
        response = await client.post(APPLICATIONS, json=REGISTRATION)
        assert PASSWORD not in response.text


async def admitted(client: AsyncClient) -> int:
    """Apply and be let in, which is what "an account exists" now means."""
    applied = await client.post(APPLICATIONS, json=REGISTRATION)
    cook_id = int(applied.json()["id"])
    await cook_access.decide(cook_id, Standing.APPROVED)
    return cook_id


class TestSignIn:
    async def test_correct_credentials_return_a_token(self, client: AsyncClient) -> None:
        await admitted(client)
        response = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["token"]

    async def test_a_wrong_password_is_unauthorised(self, client: AsyncClient) -> None:
        await admitted(client)
        response = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": "wrong-password-entirely"},
        )
        assert response.status_code == 401

    async def test_an_unknown_account_is_indistinguishable_from_a_wrong_password(
        self, client: AsyncClient
    ) -> None:
        await client.post(APPLICATIONS, json=REGISTRATION)
        unknown = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "nobody@example.com", "password": PASSWORD},
        )
        wrong = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": "wrong-password-entirely"},
        )
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json() == wrong.json()


class TestStartingWithSomething:
    async def test_the_first_cook_lands_on_a_stocked_kitchen(self, client: AsyncClient) -> None:
        """UC-10.4: an empty app is indistinguishable from a broken one."""
        created = await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        headers = {"Authorization": f"Bearer {created.json()['token']}"}

        recipes = await client.get("/api/v1/recipes", headers=headers)
        assert len(recipes.json()) > 0

    async def test_the_registry_is_stocked_too(self, client: AsyncClient) -> None:
        created = await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        headers = {"Authorization": f"Bearer {created.json()['token']}"}

        found = await client.get("/api/v1/ingredients?search=flour", headers=headers)
        assert [entry["slug"] for entry in found.json()]

    async def test_a_starter_recipe_is_readable(self, client: AsyncClient) -> None:
        created = await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        headers = {"Authorization": f"Bearer {created.json()['token']}"}

        listed = (await client.get("/api/v1/recipes", headers=headers)).json()
        first = await client.get(f"/api/v1/recipes/{listed[0]['id']}", headers=headers)
        assert first.status_code == 200
        assert first.json()["lines"]


class TestTheDoor:
    """UC-10.6. Anybody may ring the bell; an administrator answers it."""

    async def admin(self, client: AsyncClient) -> dict[str, str]:
        claimed = await client.post(
            "/api/v1/accounts/bootstrap",
            json={
                "email": "admin@example.com",
                "display_name": "Admin",
                "password": PASSWORD,
            },
        )
        return {"Authorization": f"Bearer {claimed.json()['token']}"}

    async def applicant(self, client: AsyncClient) -> int:
        applied = await client.post(APPLICATIONS, json=REGISTRATION)
        return int(applied.json()["id"])

    async def test_an_admin_sees_who_is_waiting(self, client: AsyncClient) -> None:
        headers = await self.admin(client)
        await self.applicant(client)
        waiting = await client.get(APPLICATIONS, headers=headers)
        assert [one["email"] for one in waiting.json()] == ["cook@example.com"]

    async def test_an_ordinary_cook_may_not_look(self, client: AsyncClient) -> None:
        """The queue is a list of email addresses of people who wanted in here."""
        await self.admin(client)
        cook_id = await self.applicant(client)
        await cook_access.decide(cook_id, Standing.APPROVED)
        signed_in = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": PASSWORD},
        )
        headers = {"Authorization": f"Bearer {signed_in.json()['token']}"}
        assert (await client.get(APPLICATIONS, headers=headers)).status_code == 403

    async def test_a_stranger_may_not_look(self, client: AsyncClient) -> None:
        assert (await client.get(APPLICATIONS)).status_code == 401

    async def test_approving_lets_them_sign_in(self, client: AsyncClient) -> None:
        headers = await self.admin(client)
        cook_id = await self.applicant(client)

        approved = await client.post(f"{APPLICATIONS}/{cook_id}/approved", headers=headers)
        assert approved.status_code == 200
        assert approved.json()["standing"] == "approved"

        signed_in = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": PASSWORD},
        )
        assert signed_in.status_code == 200
        assert signed_in.json()["token"]

    async def test_somebody_let_in_lands_on_a_kitchen_with_something_in_it(
        self, client: AsyncClient
    ) -> None:
        """The same reason the first admin does (UC-10.4): an empty app teaches nobody
        what it is for."""
        headers = await self.admin(client)
        cook_id = await self.applicant(client)
        await client.post(f"{APPLICATIONS}/{cook_id}/approved", headers=headers)

        signed_in = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": PASSWORD},
        )
        theirs = {"Authorization": f"Bearer {signed_in.json()['token']}"}
        assert (await client.get("/api/v1/recipes", headers=theirs)).json()

    async def test_waiting_is_told_apart_from_a_wrong_password(self, client: AsyncClient) -> None:
        """403 rather than 401: the credentials were right, so retrying them changes
        nothing and a client that treats this as "sign in again" would loop."""
        await self.admin(client)
        await self.applicant(client)
        refused = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": PASSWORD},
        )
        assert refused.status_code == 403
        assert "waiting" in refused.json()["detail"]

    async def test_being_turned_away_says_so(self, client: AsyncClient) -> None:
        """Not "still waiting", which would leave them waiting forever."""
        headers = await self.admin(client)
        cook_id = await self.applicant(client)
        await client.post(f"{APPLICATIONS}/{cook_id}/refused", headers=headers)

        refused = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": PASSWORD},
        )
        assert refused.status_code == 403
        assert "declined" in refused.json()["detail"]

    async def test_a_wrong_password_still_reveals_nothing(self, client: AsyncClient) -> None:
        """The standing is only told after the password matches, or this endpoint becomes
        a way to ask which addresses have applied here."""
        await self.admin(client)
        await self.applicant(client)
        refused = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": "wrong-password-entirely"},
        )
        assert refused.status_code == 401

    async def test_deciding_about_nobody_is_a_404(self, client: AsyncClient) -> None:
        headers = await self.admin(client)
        assert (
            await client.post(f"{APPLICATIONS}/9999/approved", headers=headers)
        ).status_code == 404
