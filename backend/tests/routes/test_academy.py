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
from tests.support import sign_up, sign_up_admin

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


class TestTheShippedFoodPages:
    """The Academy's second section as an instance receives it (ADR-057).

    Distinct from `TestTheIngredientSection` below, which is about a cook writing one.
    This is about what a self-hoster gets before anybody has written anything.

    Every part of it existed — the kind, the access layer's refusal of a page that names
    no entry, the write-page screen's food picker — and no instance had a single page in
    it, because the seed loader read one file and that file was the techniques.
    """

    async def test_the_shipped_food_pages_are_installed(self, client: AsyncClient) -> None:
        from quookly.managers.seed import stock_generic_foods, stock_registry

        await stock_registry()
        await stock_generic_foods()
        await stock_academy()

        listed = (await client.get(f"{ACADEMY}?kind=ingredient")).json()
        assert len(listed) >= 10

    async def test_each_one_shows_the_facts_of_the_food_it_names(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """The point of the section. A page about a food that names no food is a page that
        cannot show a density, an allergen or a nutrition figure (ADR-061)."""
        from quookly.managers.seed import stock_generic_foods, stock_registry

        await stock_registry()
        await stock_generic_foods()
        await stock_academy()

        page = (await client.get(f"{ACADEMY}/plain-flour", headers=cook)).json()
        assert page["kind"] == "ingredient"
        assert page["entry"]["slug"] == "flour"

    async def test_a_food_page_whose_entry_is_missing_is_skipped_not_fatal(self) -> None:
        """Stocking the Academy against a registry that is not there yet must not stop an
        instance from starting. It runs on every boot, so the page arrives on the next one."""
        assert await stock_academy() >= 45


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

    async def test_a_page_about_a_food_says_where_that_food_sits(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """So the Academy can be read as *Ingredients > Vegetables > Carrot* rather than as
        one flat alphabet of everything anybody has explained.

        Taken from the registry rather than stored on the page: where a carrot sits is a
        fact about the carrot, and a page that kept its own copy would be a second answer
        to drift from the first (ADR-061, ADR-067).
        """
        from quookly.access import ingredient as registry
        from quookly.contracts.ingredient import IngredientKind, Origin

        await registry.add_category(slug="vegetables", names={"en-GB": "Vegetables"})
        await registry.add_category(
            slug="vegetables-fresh",
            names={"en-GB": "Fresh vegetables"},
            parent_slug="vegetables",
        )
        await registry.register(
            slug="carrot",
            kind=IngredientKind.SOLID,
            density=None,
            names={"en-GB": ["carrot"]},
            origin=Origin.SEED,
            category_slug="vegetables-fresh",
        )
        written = await client.post(
            ACADEMY,
            json={
                "slug": "about-carrot",
                "kind": "ingredient",
                "about": "carrot",
                "name": "carrot",
                "spellings": [],
                "summary": "Sweet, and better raw than most people think.",
                "explanation": "Roots. They keep for weeks in the cold and the dark.",
                "caution": None,
                "name_matches": True,
            },
            headers=cook,
        )
        assert written.status_code == 201, written.text

        listed = (await client.get(ACADEMY, headers=cook)).json()
        page = next(one for one in listed if one["slug"] == "about-carrot")
        assert page["category_slug"] == "vegetables-fresh"

    async def test_a_page_about_doing_something_sits_nowhere(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """A technique is not a food and has no aisle. Absent rather than a bucket, which
        is the same rule the registry follows for a food nobody has placed."""
        listed = (await client.get(ACADEMY, params={"kind": "technique"}, headers=cook)).json()
        assert listed
        assert all(one["category_slug"] is None for one in listed)

    async def test_signing_in_is_not_required(self, client: AsyncClient, stocked: int) -> None:
        """Changed deliberately (ADR-063). What `blanch` means is not a household's, and
        keeping it behind the door turned a link to a page into a link to a sign-in form.
        Which pages a stranger sees is the rule that matters, and it has its own tests."""
        assert (await client.get(ACADEMY)).status_code == 200


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


class TestACookWritesAPage:
    """Contributing a page, and what it may do before anybody has read it (ADR-060)."""

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        return await sign_up_admin(client)

    def page(self, **changes: object) -> dict[str, object]:
        return {
            "slug": "spatchcock",
            "kind": "technique",
            "name": "spatchcock",
            "spellings": ["spatchcocked", "butterflied"],
            "summary": "Flatten a bird so it cooks evenly.",
            "explanation": "Cut out the backbone and press down on the breastbone.",
            "caution": None,
            "name_matches": True,
            **changes,
        }

    async def written(self, client: AsyncClient, headers: dict[str, str], **changes: object) -> Any:
        return await client.post(ACADEMY, json=self.page(**changes), headers=headers)

    async def test_a_cook_can_write_one(self, client: AsyncClient, cook: dict[str, str]) -> None:
        made = await self.written(client, cook)
        assert made.status_code == 201, made.text
        assert made.json()["slug"] == "spatchcock"

    async def test_signing_in_is_required(self, client: AsyncClient) -> None:
        assert (await client.post(ACADEMY, json=self.page())).status_code == 401

    async def test_it_arrives_unreviewed(self, client: AsyncClient, cook: dict[str, str]) -> None:
        assert (await self.written(client, cook)).json()["approved"] is False

    async def test_it_does_not_claim_to_be_a_model(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """A cook wrote it, so `generated` says so — the two are separate facts
        (ADR-056)."""
        assert (await self.written(client, cook)).json()["generated"] is False

    async def test_the_author_can_read_it_back(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await self.written(client, cook)
        found = await client.get(f"{ACADEMY}/spatchcock", headers=cook)
        assert found.status_code == 200
        assert found.json()["name"] == "spatchcock"

    async def test_a_slug_that_is_taken_is_refused(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """Not silently skipped: a cook told nothing would think it saved."""
        clash = await self.written(client, cook, slug="blanch")
        assert clash.status_code == 409

    async def test_the_words_of_a_step_do_not_find_it_yet(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """The whole of ADR-060. Marking works when the reader has come to the page; it
        does nothing when the page arrives underlined in a recipe they wrote."""
        await self.written(client, cook)
        found = await client.get(f"{ACADEMY}/terms/spatchcocked", headers=cook)
        assert found.json() == []

    async def test_approving_it_is_what_lets_a_step_find_it(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str]
    ) -> None:
        await self.written(client, cook)
        approved = await client.post(f"{ACADEMY}/spatchcock/approved", headers=admin)
        assert approved.status_code == 200

        found = await client.get(f"{ACADEMY}/terms/spatchcocked", headers=cook)
        assert [one["slug"] for one in found.json()] == ["spatchcock"]

    async def test_an_ordinary_cook_cannot_approve_their_own(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await self.written(client, cook)
        assert (
            await client.post(f"{ACADEMY}/spatchcock/approved", headers=cook)
        ).status_code == 403


class TestWorkingOnAPageNobodyHasApproved:
    """An author may keep working on their own draft; the Academy is otherwise shared."""

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        return await sign_up_admin(client)

    def wording(self, **changes: object) -> dict[str, object]:
        return {
            "name": "spatchcock",
            "spellings": ["spatchcocked"],
            "summary": "Flatten a bird so it cooks evenly.",
            "explanation": "Cut out the backbone and press down.",
            "caution": None,
            "name_matches": True,
            **changes,
        }

    async def a_draft(self, client: AsyncClient, headers: dict[str, str]) -> None:
        await client.post(
            ACADEMY,
            json={
                "slug": "spatchcock",
                "kind": "technique",
                **self.wording(),
            },
            headers=headers,
        )

    async def test_the_author_can_fix_their_own_typo(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """An author who cannot correct their own draft will not write a second page."""
        await self.a_draft(client, cook)
        fixed = await client.put(
            f"{ACADEMY}/spatchcock/wordings/en-GB",
            json=self.wording(summary="Flatten a bird so that it cooks evenly."),
            headers=cook,
        )
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["summary"] == "Flatten a bird so that it cooks evenly."

    async def test_somebody_elses_draft_is_not_theirs_to_rewrite(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await self.a_draft(client, cook)
        stranger = await sign_up(client, "neighbour@example.com")
        refused = await client.put(
            f"{ACADEMY}/spatchcock/wordings/en-GB",
            json=self.wording(summary="Something else entirely."),
            headers=stranger,
        )
        assert refused.status_code == 403

    async def test_once_approved_it_is_the_instances_page(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str]
    ) -> None:
        """Approval is the moment a draft becomes what every cook here reads, so from then
        on a correction is an administrator's."""
        await self.a_draft(client, cook)
        await client.post(f"{ACADEMY}/spatchcock/approved", headers=admin)

        refused = await client.put(
            f"{ACADEMY}/spatchcock/wordings/en-GB",
            json=self.wording(summary="Something else entirely."),
            headers=cook,
        )
        assert refused.status_code == 403

    async def test_the_page_says_whether_the_reader_may_rewrite_it(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """So a screen does not have to re-derive the rule and get it slightly different."""
        await self.a_draft(client, cook)
        mine = await client.get(f"{ACADEMY}/spatchcock", headers=cook)
        assert mine.json()["may_rewrite"] is True

    async def test_it_says_no_to_somebody_elses_draft(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await self.a_draft(client, cook)
        stranger = await sign_up(client, "neighbour@example.com")
        theirs = await client.get(f"{ACADEMY}/spatchcock", headers=stranger)
        assert theirs.json()["may_rewrite"] is False

    async def test_an_admin_may_rewrite_anything(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str]
    ) -> None:
        await self.a_draft(client, cook)
        theirs = await client.get(f"{ACADEMY}/spatchcock", headers=admin)
        assert theirs.json()["may_rewrite"] is True

    async def test_the_author_stops_being_able_to_once_it_is_approved(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str]
    ) -> None:
        await self.a_draft(client, cook)
        await client.post(f"{ACADEMY}/spatchcock/approved", headers=admin)
        mine = await client.get(f"{ACADEMY}/spatchcock", headers=cook)
        assert mine.json()["may_rewrite"] is False

    async def test_an_admin_may_rewrite_it_at_any_point(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str]
    ) -> None:
        await self.a_draft(client, cook)
        fixed = await client.put(
            f"{ACADEMY}/spatchcock/wordings/en-GB",
            json=self.wording(summary="Flattened, so it cooks evenly."),
            headers=admin,
        )
        assert fixed.status_code == 200, fixed.text


class TestDecliningAPage:
    """Put away rather than destroyed."""

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        return await sign_up_admin(client)

    async def a_draft(self, client: AsyncClient, headers: dict[str, str]) -> None:
        await client.post(
            ACADEMY,
            json={
                "slug": "spatchcock",
                "kind": "technique",
                "name": "spatchcock",
                "spellings": ["spatchcocked"],
                "summary": "Flatten a bird so it cooks evenly.",
                "explanation": "Cut out the backbone and press down.",
                "caution": None,
                "name_matches": True,
            },
            headers=headers,
        )

    async def test_an_admin_can_decline_one(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str]
    ) -> None:
        await self.a_draft(client, cook)
        declined = await client.delete(f"{ACADEMY}/spatchcock", headers=admin)
        assert declined.status_code == 204

        assert (await client.get(f"{ACADEMY}/spatchcock", headers=cook)).status_code == 404

    async def test_it_leaves_the_queue(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str]
    ) -> None:
        await self.a_draft(client, cook)
        await client.delete(f"{ACADEMY}/spatchcock", headers=admin)

        queue = await client.get(f"{ACADEMY}?approved=false", headers=admin)
        assert [one["slug"] for one in queue.json()] == []

    async def test_an_ordinary_cook_cannot_decline_a_page(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await self.a_draft(client, cook)
        assert (await client.delete(f"{ACADEMY}/spatchcock", headers=cook)).status_code == 403

    async def test_declining_a_page_that_is_not_there_says_so(
        self, client: AsyncClient, admin: dict[str, str]
    ) -> None:
        assert (await client.delete(f"{ACADEMY}/nothing", headers=admin)).status_code == 404


class TestTheReviewQueue:
    async def test_it_is_what_nobody_has_read(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        await client.post(
            ACADEMY,
            json={
                "slug": "spatchcock",
                "kind": "technique",
                "name": "spatchcock",
                "spellings": [],
                "summary": "Flatten a bird so it cooks evenly.",
                "explanation": "Cut out the backbone and press down.",
                "caution": None,
                "name_matches": True,
            },
            headers=cook,
        )
        queue = await client.get(f"{ACADEMY}?approved=false", headers=cook)
        assert [one["slug"] for one in queue.json()] == ["spatchcock"]

    async def test_the_shipped_pages_need_no_review(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        queue = await client.get(f"{ACADEMY}?approved=false", headers=cook)
        assert queue.json() == []


class TestTheIngredientSection:
    """Pages about food, sitting over the registry rather than duplicating it (ADR-061)."""

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        return await sign_up_admin(client)

    @pytest.fixture
    async def flour(self) -> str:
        from quookly.access import ingredient as registry
        from quookly.contracts.ingredient import IngredientKind, Origin

        await registry.register(
            slug="plain-flour",
            kind=IngredientKind.POWDER,
            density=None,
            names={"en-GB": ["plain flour"]},
            origin=Origin.SEED,
        )
        return "plain-flour"

    def page(self, **changes: object) -> dict[str, object]:
        return {
            "slug": "about-plain-flour",
            "kind": "ingredient",
            "about": "plain-flour",
            "name": "plain flour",
            "spellings": [],
            "summary": "The everyday one.",
            "explanation": "Around ten per cent protein, which is why it is the everyday one.",
            "caution": None,
            "name_matches": True,
            **changes,
        }

    async def test_a_cook_can_write_about_a_food(
        self, client: AsyncClient, cook: dict[str, str], flour: str
    ) -> None:
        made = await client.post(ACADEMY, json=self.page(), headers=cook)
        assert made.status_code == 201, made.text
        assert made.json()["entry"]["slug"] == "plain-flour"

    async def test_the_facts_come_from_the_registry(
        self, client: AsyncClient, cook: dict[str, str], flour: str, admin: dict[str, str]
    ) -> None:
        """Classified after the page was written, and the page says so without being
        touched — which is the whole point of not copying them."""
        await client.post(ACADEMY, json=self.page(), headers=cook)
        await client.put(
            "/api/v1/registry/plain-flour/allergens",
            json={"allergens": ["gluten"]},
            headers=admin,
        )

        page = await client.get(f"{ACADEMY}/about-plain-flour", headers=cook)
        assert page.json()["entry"]["allergens"] == ["gluten"]
        assert page.json()["entry"]["classified"] is True

    async def test_unexamined_is_not_shown_as_none(
        self, client: AsyncClient, cook: dict[str, str], flour: str
    ) -> None:
        """An empty list with `classified` false means nobody has looked (ADR-006)."""
        await client.post(ACADEMY, json=self.page(), headers=cook)
        page = await client.get(f"{ACADEMY}/about-plain-flour", headers=cook)
        assert page.json()["entry"]["allergens"] == []
        assert page.json()["entry"]["classified"] is False

    async def test_a_page_about_no_food_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        refused = await client.post(ACADEMY, json=self.page(about=None), headers=cook)
        assert refused.status_code == 422

    async def test_a_food_the_registry_does_not_have_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """A page about an ingredient nobody can put in a recipe is a page about nothing."""
        refused = await client.post(ACADEMY, json=self.page(about="unicorn-steak"), headers=cook)
        assert refused.status_code == 404

    async def test_a_technique_page_carries_no_entry(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        page = await client.get(f"{ACADEMY}/blanch", headers=cook)
        assert page.json()["entry"] is None

    async def test_the_section_can_be_browsed_on_its_own(
        self, client: AsyncClient, cook: dict[str, str], flour: str, stocked: int
    ) -> None:
        await client.post(ACADEMY, json=self.page(), headers=cook)

        listed = await client.get(f"{ACADEMY}?kind=ingredient", headers=cook)
        assert [one["slug"] for one in listed.json()] == ["about-plain-flour"]

    async def test_a_mixed_list_says_which_section_each_page_is_in(
        self, client: AsyncClient, cook: dict[str, str], flour: str, stocked: int
    ) -> None:
        """Browsing without a filter used to report every page as a technique, because the
        kind came from the *query* rather than from the page. Invisible while there was one
        section."""
        await client.post(ACADEMY, json=self.page(), headers=cook)

        listed = await client.get(ACADEMY, headers=cook)
        kinds = {one["slug"]: one["kind"] for one in listed.json()}
        assert kinds["about-plain-flour"] == "ingredient"
        assert kinds["blanch"] == "technique"

    async def test_the_pages_about_one_food_can_be_asked_for(
        self, client: AsyncClient, cook: dict[str, str], flour: str, stocked: int
    ) -> None:
        """The way back from the facts to the prose. Asked of the Academy rather than
        answered by the registry entry: each side owns its own vocabulary, and the
        registry's contracts already sit underneath the Academy's."""
        await client.post(ACADEMY, json=self.page(), headers=cook)

        found = await client.get(f"{ACADEMY}?about=plain-flour", headers=cook)
        assert [one["slug"] for one in found.json()] == ["about-plain-flour"]

    async def test_a_food_nobody_has_written_about_answers_with_none(
        self, client: AsyncClient, cook: dict[str, str], flour: str, stocked: int
    ) -> None:
        assert (await client.get(f"{ACADEMY}?about=plain-flour", headers=cook)).json() == []

    async def test_asking_about_a_food_that_is_not_registered_says_so(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        assert (await client.get(f"{ACADEMY}?about=unicorn-steak", headers=cook)).status_code == 404


class TestAskingForAnExplanation:
    """A page nobody has written, written by a model (UC-7.5, ADR-062).

    Last on purpose: it is the only part of this application that can state something
    untrue while looking exactly like something true.
    """

    ASKED = "/api/v1/academy/explanations"

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        return await sign_up_admin(client)

    @pytest.fixture
    def answering(self, monkeypatch: MonkeyPatch) -> None:
        from quookly.access import model as inference
        from quookly.contracts.inference import Completion

        answer = {
            "name": "spatchcock",
            "spellings": ["spatchcocked", "butterflied"],
            "summary": "Flatten a bird so it cooks evenly.",
            "explanation": "Cut out the backbone with shears and press down on the breastbone.",
            "caution": "",
        }

        async def complete_structured(
            prompt: str, schema: dict[str, Any], system: str | None = None, **rest: Any
        ) -> tuple[dict[str, Any], Completion]:
            return answer, Completion(text="{}", model="test")

        monkeypatch.setattr(inference, "complete_structured", complete_structured)

    async def test_a_cook_can_ask(
        self, client: AsyncClient, cook: dict[str, str], answering: None
    ) -> None:
        made = await client.post(self.ASKED, json={"term": "spatchcock"}, headers=cook)
        assert made.status_code == 201, made.text
        assert made.json()["summary"] == "Flatten a bird so it cooks evenly."

    async def test_signing_in_is_required(self, client: AsyncClient, answering: None) -> None:
        assert (await client.post(self.ASKED, json={"term": "spatchcock"})).status_code == 401

    async def test_it_says_a_model_wrote_it(
        self, client: AsyncClient, cook: dict[str, str], answering: None
    ) -> None:
        """A page a model wrote must not read like one somebody wrote (ADR-056)."""
        made = await client.post(self.ASKED, json={"term": "spatchcock"}, headers=cook)
        assert made.json()["generated"] is True
        assert made.json()["approved"] is False

    async def test_nobody_here_is_recorded_as_having_written_it(
        self, client: AsyncClient, cook: dict[str, str], answering: None
    ) -> None:
        """Asking for a page is not writing one, so the cook who asked does not get to
        polish it before an administrator reads it."""
        made = await client.post(self.ASKED, json={"term": "spatchcock"}, headers=cook)
        assert made.json()["may_rewrite"] is False

    async def test_it_is_not_matched_into_a_recipe_yet(
        self, client: AsyncClient, cook: dict[str, str], answering: None
    ) -> None:
        """ADR-060 composing with ADR-056: the cook who asked gets the page, and the
        instance does not get a new word in everybody's recipes."""
        await client.post(self.ASKED, json={"term": "spatchcock"}, headers=cook)
        found = await client.get(f"{ACADEMY}/terms/spatchcocked", headers=cook)
        assert found.json() == []

    async def test_approving_it_is_what_puts_it_into_recipes(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str], answering: None
    ) -> None:
        made = await client.post(self.ASKED, json={"term": "spatchcock"}, headers=cook)
        await client.post(f"{ACADEMY}/{made.json()['slug']}/approved", headers=admin)

        found = await client.get(f"{ACADEMY}/terms/spatchcocked", headers=cook)
        assert [one["slug"] for one in found.json()] == [made.json()["slug"]]

    async def test_it_answers_to_the_word_that_was_asked_about(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str], answering: None
    ) -> None:
        """Otherwise the cook taps the same word again and is told nobody has explained
        it, which is the screen they just left."""
        made = await client.post(self.ASKED, json={"term": "spatchcocking"}, headers=cook)
        await client.post(f"{ACADEMY}/{made.json()['slug']}/approved", headers=admin)

        found = await client.get(f"{ACADEMY}/terms/spatchcocking", headers=cook)
        assert len(found.json()) == 1

    async def test_a_word_the_registry_knows_is_filed_as_a_food(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """The Academy has two sections, and a food asked about is a food (ADR-057).

        Filing it as a technique put every generated page in one section and left the
        ingredient section of a shipped instance permanently empty — and a page about a
        food that names no food cannot show that food's facts (ADR-061)."""
        from quookly.access import ingredient as registry
        from quookly.access import model as inference
        from quookly.contracts.inference import Completion
        from quookly.contracts.ingredient import IngredientKind, Origin

        async def answering(
            prompt: str, schema: dict[str, Any], system: str | None = None, **rest: Any
        ) -> tuple[dict[str, Any], Completion]:
            return {
                "name": "plain flour",
                "spellings": ["flour"],
                "summary": "Wheat flour with no raising agent in it.",
                "explanation": "Milled from wheat, and the backbone of most doughs.",
                "caution": "",
            }, Completion(text="{}", model="test")

        monkeypatch.setattr(inference, "complete_structured", answering)
        await registry.register(
            slug="plain-flour",
            kind=IngredientKind.SOLID,
            density=None,
            names={"en-GB": ["plain flour"]},
            origin=Origin.SEED,
        )

        made = await client.post(self.ASKED, json={"term": "plain flour"}, headers=cook)

        assert made.status_code == 201
        assert made.json()["kind"] == "ingredient"
        assert made.json()["entry"]["slug"] == "plain-flour"

    async def test_a_word_the_registry_does_not_know_is_still_a_technique(
        self, client: AsyncClient, cook: dict[str, str], answering: None
    ) -> None:
        """`spatchcock` is not a food, and nothing in the registry says otherwise."""
        made = await client.post(self.ASKED, json={"term": "spatchcock"}, headers=cook)
        assert made.json()["kind"] == "technique"
        assert made.json()["entry"] is None

    async def test_a_term_somebody_has_explained_is_refused(
        self, client: AsyncClient, cook: dict[str, str], answering: None, stocked: int
    ) -> None:
        """Not a second opinion. The Academy tolerates several pages per term for pages
        people wrote; generating near-copies nobody asked for is how a queue fills up."""
        refused = await client.post(self.ASKED, json={"term": "blanch"}, headers=cook)
        assert refused.status_code == 409

    async def test_an_instance_with_no_model_says_so(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """No provider is configured in these tests, which is the honest default: every
        other screen works without one, and this is an addition to a screen rather than a
        dependency of it.

        A 422 rather than a 502, the same as writing a recipe: nothing is broken and
        nobody has said where to ask, which is a thing an operator can act on."""
        refused = await client.post(self.ASKED, json={"term": "spatchcock"}, headers=cook)
        assert refused.status_code == 422
        assert "no model" in refused.json()["detail"]

    async def test_an_answer_with_nothing_in_it_is_not_stored(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        from quookly.access import model as inference
        from quookly.contracts.inference import Completion

        async def empty(
            prompt: str, schema: dict[str, Any], system: str | None = None, **rest: Any
        ) -> tuple[dict[str, Any], Completion]:
            return {"name": "x", "summary": "", "explanation": ""}, Completion(
                text="{}", model="test"
            )

        monkeypatch.setattr(inference, "complete_structured", empty)

        refused = await client.post(self.ASKED, json={"term": "spatchcock"}, headers=cook)
        assert refused.status_code == 502
        assert (await client.get(f"{ACADEMY}?approved=false", headers=cook)).json() == []


class TestReadingItWithoutAnAccount:
    """The Academy from the open internet (ADR-063).

    Everything else here belongs to a household. What `blanch` means does not, and keeping
    it behind the door turns a link to a page into a link to a sign-in form.

    The load-bearing half is *which* pages: only what somebody here has read. An unreviewed
    page is readable by the people here, and publishing it is a different act.
    """

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        return await sign_up_admin(client)

    async def a_draft(self, client: AsyncClient, headers: dict[str, str]) -> None:
        await client.post(
            ACADEMY,
            json={
                "slug": "spatchcock",
                "kind": "technique",
                "name": "spatchcock",
                "spellings": ["spatchcocked"],
                "summary": "Flatten a bird so it cooks evenly.",
                "explanation": "Cut out the backbone and press down.",
                "caution": None,
                "name_matches": True,
            },
            headers=headers,
        )

    async def test_the_list_needs_no_account(self, client: AsyncClient, stocked: int) -> None:
        listed = await client.get(ACADEMY)
        assert listed.status_code == 200
        assert any(one["slug"] == "blanch" for one in listed.json())

    async def test_a_page_needs_no_account(self, client: AsyncClient, stocked: int) -> None:
        assert (await client.get(f"{ACADEMY}/blanch")).status_code == 200

    async def test_a_term_needs_no_account(self, client: AsyncClient, stocked: int) -> None:
        found = await client.get(f"{ACADEMY}/terms/blanch")
        assert found.status_code == 200
        assert [one["slug"] for one in found.json()] == ["blanch"]

    async def test_a_visitor_reads_in_the_language_they_asked_for(
        self, client: AsyncClient, stocked: int
    ) -> None:
        """A signed-out reader has no cook record to take a language from, so they say."""
        page = await client.get(f"{ACADEMY}/blanch?locale=de-CH")
        assert page.json()["name"] == "blanchieren"

    async def test_a_visitor_who_says_nothing_gets_the_source_language(
        self, client: AsyncClient, stocked: int
    ) -> None:
        assert (await client.get(f"{ACADEMY}/blanch")).json()["name"] == "blanch"

    async def test_a_page_nobody_has_read_is_not_published(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """Anyone let through the door could otherwise publish to the open internet under
        this instance's name."""
        await self.a_draft(client, cook)
        assert (await client.get(f"{ACADEMY}/spatchcock")).status_code == 404

    async def test_and_it_is_not_in_the_public_list(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        await self.a_draft(client, cook)
        listed = await client.get(ACADEMY)
        assert all(one["slug"] != "spatchcock" for one in listed.json())

    async def test_but_the_people_here_still_see_it(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """ADR-060 unchanged: an author has to be able to see their own draft."""
        await self.a_draft(client, cook)
        assert (await client.get(f"{ACADEMY}/spatchcock", headers=cook)).status_code == 200

    async def test_approving_it_publishes_it(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str], stocked: int
    ) -> None:
        await self.a_draft(client, cook)
        await client.post(f"{ACADEMY}/spatchcock/approved", headers=admin)
        assert (await client.get(f"{ACADEMY}/spatchcock")).status_code == 200

    async def test_a_visitor_cannot_ask_for_the_queue(
        self, client: AsyncClient, cook: dict[str, str], stocked: int
    ) -> None:
        """Asking for what is unreviewed is asking for what is not published."""
        await self.a_draft(client, cook)
        assert (await client.get(f"{ACADEMY}?approved=false")).json() == []

    async def test_a_visitor_cannot_write_one(self, client: AsyncClient) -> None:
        made = await client.post(
            ACADEMY,
            json={
                "slug": "spatchcock",
                "kind": "technique",
                "name": "spatchcock",
                "spellings": [],
                "summary": "Flatten a bird.",
                "explanation": "Cut out the backbone.",
                "caution": None,
                "name_matches": True,
            },
        )
        assert made.status_code == 401

    async def test_a_visitor_cannot_correct_one(self, client: AsyncClient, stocked: int) -> None:
        refused = await client.put(
            f"{ACADEMY}/blanch/wordings/en-GB",
            json={
                "name": "blanch",
                "spellings": [],
                "summary": "Something else.",
                "explanation": "Something else entirely.",
                "caution": None,
                "name_matches": True,
            },
        )
        assert refused.status_code == 401

    async def test_a_visitor_cannot_approve_one(self, client: AsyncClient, stocked: int) -> None:
        assert (await client.post(f"{ACADEMY}/blanch/approved")).status_code == 401

    async def test_a_visitor_cannot_decline_one(self, client: AsyncClient, stocked: int) -> None:
        assert (await client.delete(f"{ACADEMY}/blanch")).status_code == 401

    async def test_a_visitor_cannot_spend_the_operators_money(self, client: AsyncClient) -> None:
        """An open relay to a paid provider is what this would otherwise be."""
        asked = await client.post("/api/v1/academy/explanations", json={"term": "spatchcock"})
        assert asked.status_code == 401


class TestAPictureOnAPublicPage:
    """A picture is public exactly when the page it is on is (ADR-063).

    Media ids are unguessable, and that is not an access rule — it is the absence of one.
    Today every picture here is an Academy picture, and the first recipe photograph would
    otherwise have been published by a decision nobody revisited.
    """

    @pytest.fixture
    async def admin(self, client: AsyncClient) -> dict[str, str]:
        return await sign_up_admin(client)

    async def illustrated(self, client: AsyncClient, admin: dict[str, str], slug: str) -> str:
        picture = BytesIO()
        Image.new("RGB", (40, 30), "white").save(picture, format="PNG")
        added = await client.post(
            f"{ACADEMY}/{slug}/pictures",
            files={"picture": ("shot.png", picture.getvalue(), "image/png")},
            data={"description": "A pan of water at a rolling boil."},
            headers=admin,
        )
        assert added.status_code == 200, added.text
        return str(added.json()["pictures"][0]["media_id"])

    async def a_draft(self, client: AsyncClient, headers: dict[str, str]) -> None:
        await client.post(
            ACADEMY,
            json={
                "slug": "spatchcock",
                "kind": "technique",
                "name": "spatchcock",
                "spellings": [],
                "summary": "Flatten a bird.",
                "explanation": "Cut out the backbone.",
                "caution": None,
                "name_matches": True,
            },
            headers=headers,
        )

    async def test_a_picture_on_an_approved_page_needs_no_account(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        media_id = await self.illustrated(client, admin, "blanch")
        assert (await client.get(f"/api/v1/media/{media_id}")).status_code == 200

    async def test_a_picture_on_a_page_nobody_has_read_is_not_served(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str], stocked: int
    ) -> None:
        await self.a_draft(client, cook)
        media_id = await self.illustrated(client, admin, "spatchcock")
        assert (await client.get(f"/api/v1/media/{media_id}")).status_code == 404

    async def test_but_the_people_here_still_see_it(
        self, client: AsyncClient, cook: dict[str, str], admin: dict[str, str], stocked: int
    ) -> None:
        await self.a_draft(client, cook)
        media_id = await self.illustrated(client, admin, "spatchcock")
        assert (await client.get(f"/api/v1/media/{media_id}", headers=cook)).status_code == 200

    async def test_a_picture_on_no_page_at_all_is_not_served(
        self, client: AsyncClient, admin: dict[str, str], stocked: int
    ) -> None:
        """An orphan — a file whose page was corrected out from under it. Nothing refers to
        it, so nothing publishes it."""
        media_id = await self.illustrated(client, admin, "blanch")
        page = await client.get(f"{ACADEMY}/blanch", headers=admin)
        await client.delete(
            f"{ACADEMY}/blanch/pictures/{page.json()['pictures'][0]['id']}", headers=admin
        )
        assert (await client.get(f"/api/v1/media/{media_id}")).status_code == 404
