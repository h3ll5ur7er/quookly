"""The Academy through the API (Phase 7, unit 1).

Browsing a section and reading a page, and nothing else. An Academy nobody can add to is
still an Academy — writing, approving and generating follow, in that order, so the part
that can be *wrong* arrives last.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
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
