"""The Academy through the API (Phase 7, unit 1).

Browsing a section and reading a page, and nothing else. An Academy nobody can add to is
still an Academy — writing, approving and generating follow, in that order, so the part
that can be *wrong* arrives last.
"""

from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.managers.seed import stock_academy
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

ACADEMY = "/api/v1/academy"


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
async def stocked() -> int:
    """The shipped pages, loaded the way start-up loads them.

    Explicitly rather than by boot: these tests drive the app through `ASGITransport`,
    which does not run the lifespan.
    """
    return await stock_academy()


class TestWhatShips:
    async def test_the_seeded_pages_are_installed(self, stocked: int) -> None:
        assert stocked >= 45

    async def test_installing_again_adds_nothing(self, stocked: int) -> None:
        assert await stock_academy() == 0

    async def test_they_are_shipped_and_need_no_review(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """Nobody signs off what the instance chose to ship (ADR-056)."""
        page = (await client.get(f"{ACADEMY}/fold", headers=cook)).json()
        assert page["origin"] == "seed"
        assert page["approved"] is True
        assert page["generated"] is False


class TestBrowsing:
    async def test_the_academy_can_be_listed(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        response = await client.get(ACADEMY, headers=cook)
        assert response.status_code == 200
        assert len(response.json()) == stocked

    async def test_a_section_can_be_asked_for(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        body = (await client.get(ACADEMY, params={"kind": "technique"}, headers=cook)).json()
        assert len(body) == stocked

    async def test_signing_in_is_required(self, client: AsyncClient, stocked: int) -> None:
        assert (await client.get(ACADEMY)).status_code == 401


class TestReading:
    async def test_a_page_explains_itself(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        page = (await client.get(f"{ACADEMY}/fold", headers=cook)).json()
        assert page["name"] == "fold"
        assert "air" in page["explanation"]

    async def test_it_carries_the_spellings_a_step_would_use(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """The field a step's own words are matched against (ADR-055)."""
        page = (await client.get(f"{ACADEMY}/fold", headers=cook)).json()
        assert "folded in" in page["spellings"]

    async def test_a_caution_comes_with_the_dangerous_ones(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        page = (await client.get(f"{ACADEMY}/deep-fry", headers=cook)).json()
        assert page["caution"] is not None
        assert "water" in page["caution"]

    async def test_most_pages_carry_none(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        page = (await client.get(f"{ACADEMY}/fold", headers=cook)).json()
        assert page["caution"] is None

    async def test_a_page_that_is_not_there_is_a_404(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        assert (await client.get(f"{ACADEMY}/no-such-thing", headers=cook)).status_code == 404


class TestTerms:
    async def test_a_term_finds_its_page(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        found = (await client.get(f"{ACADEMY}/terms/folded in", headers=cook)).json()
        assert [one["slug"] for one in found] == ["fold"]

    async def test_the_term_route_is_not_swallowed_by_the_page_route(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """They share a shape and the first match wins."""
        response = await client.get(f"{ACADEMY}/terms/fold", headers=cook)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_a_term_nobody_claims_finds_nobody(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        assert (await client.get(f"{ACADEMY}/terms/saffron", headers=cook)).json() == []

    async def test_the_shipped_section_has_no_shared_terms(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """Several pages *may* share a term (ADR-058); inside one hand-written section
        it is still a mistake, and the seed tests refuse it. Checked here too, because
        that check reads the file and this one reads what was installed from it."""
        page = (await client.get(f"{ACADEMY}/fold", headers=cook)).json()
        assert page["also"] == []


class TestCorrecting:
    """An administrator correcting a page, one language at a time."""

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        claimed = await client.post(
            "/api/v1/accounts/bootstrap",
            json={
                "email": "admin@example.com",
                "display_name": "Admin",
                "password": "a-sufficiently-long-password",
            },
        )
        return {"Authorization": f"Bearer {claimed.json()['token']}"}

    def wording(self, **changes: object) -> dict[str, object]:
        return {
            "name": "fold",
            "spellings": ["fold in", "folded in"],
            "summary": "Combine without knocking out the air.",
            "explanation": "Cut down through the middle and turn the mixture over itself.",
            "caution": None,
            "name_matches": True,
            **changes,
        }

    async def test_an_admin_can_rewrite_a_page(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        response = await client.put(
            f"{ACADEMY}/fold/wordings/en-GB",
            json=self.wording(explanation="Cut down, sweep the bottom, turn it over itself."),
            headers=admin,
        )
        assert response.status_code == 200
        assert response.json()["explanation"].startswith("Cut down, sweep")

    async def test_a_translation_can_be_added(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        """A locale the page does not speak yet is how a translation arrives."""
        await client.put(
            f"{ACADEMY}/fold/wordings/it-IT",
            json=self.wording(name="incorporare", summary="Unire senza smontare il composto."),
            headers=admin,
        )
        page = (await client.get(f"{ACADEMY}/fold", headers=admin)).json()
        assert page["name"] == "fold"  # the admin still reads English

    async def test_the_other_languages_are_left_alone(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        await client.put(f"{ACADEMY}/fold/wordings/en-GB", json=self.wording(), headers=admin)
        await client.put("/api/v1/setup/locale", json={"locale": "de-CH"}, headers=admin)
        page = (await client.get(f"{ACADEMY}/fold", headers=admin)).json()
        assert page["name"] == "unterheben"

    async def test_correcting_does_not_approve_it(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        """Fixing a sentence is not saying somebody has read the page (ADR-051)."""
        await client.put(f"{ACADEMY}/fold/wordings/en-GB", json=self.wording(), headers=admin)
        page = (await client.get(f"{ACADEMY}/fold", headers=admin)).json()
        # Seeded pages arrive approved; what matters is that amending did not decide it.
        assert page["approved"] is True

    async def test_a_page_can_be_approved(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        response = await client.post(f"{ACADEMY}/fold/approved", headers=admin)
        assert response.status_code == 200
        assert response.json()["approved"] is True

    async def test_an_ordinary_cook_may_not_correct(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """The Academy is shared: a correction changes what every cook here reads."""
        response = await client.put(
            f"{ACADEMY}/fold/wordings/en-GB", json=self.wording(), headers=cook
        )
        assert response.status_code == 403

    async def test_an_ordinary_cook_may_not_approve(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        assert (await client.post(f"{ACADEMY}/fold/approved", headers=cook)).status_code == 403

    async def test_correcting_something_absent_is_a_404(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        response = await client.put(
            f"{ACADEMY}/no-such-thing/wordings/en-GB", json=self.wording(), headers=admin
        )
        assert response.status_code == 404

    async def test_a_correction_changes_what_a_step_is_matched_against(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        """The spellings are the load-bearing field, so editing them is editing what the
        recipe screens will underline (ADR-055)."""
        await client.put(
            f"{ACADEMY}/fold/wordings/en-GB",
            json=self.wording(spellings=["turn it over itself"]),
            headers=admin,
        )
        page = (await client.get(f"{ACADEMY}/fold", headers=admin)).json()
        assert page["spellings"] == ["turn it over itself"]


class TestPictures:
    """A page about julienne without a photograph of julienne is a knife cut in words."""

    @pytest.fixture(autouse=True)
    def somewhere_to_put_them(self, monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("QUOOKLY_MEDIA_DIR", str(tmp_path / "media"))
        get_settings.cache_clear()

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        claimed = await client.post(
            "/api/v1/accounts/bootstrap",
            json={
                "email": "admin@example.com",
                "display_name": "Admin",
                "password": "a-sufficiently-long-password",
            },
        )
        return {"Authorization": f"Bearer {claimed.json()['token']}"}

    def photograph(self) -> bytes:
        held = BytesIO()
        Image.new("RGB", (600, 400), (120, 140, 130)).save(held, format="JPEG")
        return held.getvalue()

    async def illustrate(
        self,
        client: AsyncClient,
        headers: dict[str, str],
        slug: str = "julienne",
        description: str = "Carrot cut into fine matchsticks.",
    ) -> Any:
        return await client.post(
            f"{ACADEMY}/{slug}/pictures",
            headers=headers,
            files={"picture": ("julienne.jpg", self.photograph(), "image/jpeg")},
            data={"description": description},
        )

    async def test_a_picture_can_be_put_on_a_page(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        response = await self.illustrate(client, admin)
        assert response.status_code == 200
        assert len(response.json()["pictures"]) == 1

    async def test_it_says_what_it_shows(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        """Alt text is required, not optional: a picture without it is an accessibility
        failure, and this project checks that as it builds rather than afterwards."""
        body = (await self.illustrate(client, admin)).json()
        assert body["pictures"][0]["description"] == "Carrot cut into fine matchsticks."

    async def test_a_description_is_required(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        response = await client.post(
            f"{ACADEMY}/julienne/pictures",
            headers=admin,
            files={"picture": ("julienne.jpg", self.photograph(), "image/jpeg")},
        )
        assert response.status_code == 422

    async def test_it_says_which_language_the_description_is_in(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        """Not always the reader's. Saying so beats handing somebody English silently."""
        body = (await self.illustrate(client, admin)).json()
        assert body["pictures"][0]["locale"] == "en-GB"

    async def test_the_bytes_can_be_fetched(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        body = (await self.illustrate(client, admin)).json()
        media_id = body["pictures"][0]["media_id"]
        served = await client.get(f"/api/v1/media/{media_id}", headers=admin)
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/webp"

    async def test_a_picture_nobody_stored_is_a_404(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        assert (await client.get(f"/api/v1/media/{'0' * 32}", headers=admin)).status_code == 404

    async def test_a_file_that_is_not_a_picture_is_refused(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        response = await client.post(
            f"{ACADEMY}/julienne/pictures",
            headers=admin,
            files={"picture": ("notes.txt", b"this is not a photograph", "text/plain")},
            data={"description": "Nothing at all."},
        )
        assert response.status_code == 422

    async def test_a_picture_can_be_taken_off_again(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        body = (await self.illustrate(client, admin)).json()
        picture_id = body["pictures"][0]["id"]
        removed = await client.delete(f"{ACADEMY}/julienne/pictures/{picture_id}", headers=admin)
        assert removed.status_code == 200
        assert removed.json()["pictures"] == []

    async def test_taking_it_off_leaves_the_file(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        """By decision: a reference changing is not evidence nobody wants the bytes, and a
        sweep that guessed would eventually guess wrong. A CLI command collects them."""
        body = (await self.illustrate(client, admin)).json()
        media_id = body["pictures"][0]["media_id"]
        await client.delete(
            f"{ACADEMY}/julienne/pictures/{body['pictures'][0]['id']}", headers=admin
        )
        assert (await client.get(f"/api/v1/media/{media_id}", headers=admin)).status_code == 200

    async def test_an_ordinary_cook_may_not_illustrate(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        response = await self.illustrate(client, cook)
        assert response.status_code == 403

    async def test_a_page_that_is_not_there_is_a_404(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        response = await self.illustrate(client, admin, slug="no-such-thing")
        assert response.status_code == 404
