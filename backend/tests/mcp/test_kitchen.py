"""The MCP surface, driven by a real MCP client (ADR-068).

Not by calling the tool functions: what an agent gets is a *tool list* with descriptions
and schemas, and half of what this surface has to get right is in those descriptions.
A test that called the functions directly would pass while the server advertised nothing.

The scenario these exist for: a friend is coming over, there is a game on, and the agent
should find something that needs no shopping trip — then write a new recipe out of what is
about to go off, in the registry's own vocabulary, so nobody has to merge anything
afterwards.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
import pytest
from httpx import ASGITransport, AsyncClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import academy
from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.mcp import agent_app, kitchen
from quookly.utilities.configuration import get_settings
from tests.support import sign_up


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as made:
        yield made


@pytest.fixture
async def cook(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "chef@example.com")


@pytest.fixture
async def stocked() -> None:
    """Two foods, so a recipe can be written about something."""
    await registry.register(
        slug="plain-flour",
        kind=IngredientKind.POWDER,
        density=None,
        names={"en-GB": ["plain flour"]},
        origin=Origin.SEED,
    )
    await registry.register(
        slug="tomato",
        kind=IngredientKind.SOLID,
        density=None,
        names={"en-GB": ["tomato"]},
        origin=Origin.SEED,
    )


@asynccontextmanager
async def talking(headers: dict[str, str]) -> AsyncIterator[Any]:
    """An MCP session over the app itself, with no socket in the middle.

    The transport is ASGI rather than a real port, which is not only faster: it is the
    claim ADR-068 makes, tested. If these tools needed a running server they would be a
    second client, and the whole argument for mounting them here would be gone.

    A **fresh** surface per test, not the one the application mounts. A session manager may
    be run once, and every test here has its own event loop, so sharing one would work for
    exactly the first test — which is how it read the first time.

    The task group is started here rather than in a fixture, because starting it in one
    puts its cancel scope in a different task from the requests, and anyio refuses that in
    a message that takes a while to recognise.
    """
    surface = agent_app()
    async with (
        kitchen.session_manager.run(),
        streamable_http_client(
            "http://testserver/",
            http_client=httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=surface),
                base_url="http://testserver",
                headers=headers,
                # As the SDK's own client does. Mounting at `/mcp` means a bare `/mcp`
                # is a 307 to `/mcp/`, which every MCP client follows and this one has to
                # as well, or it is testing a client nobody uses.
                follow_redirects=True,
            ),
        ) as streams,
    ):
        yield streams


class TestWhatAnAgentIsOffered:
    async def test_the_tools_are_listed(self, cook: dict[str, str], stocked: None) -> None:
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()

        offered = {tool.name for tool in listed.tools}
        assert "what_could_i_cook" in offered
        assert "what_is_in_the_pantry" in offered
        assert "find_a_food" in offered

    async def test_every_tool_says_what_it_does(self, cook: dict[str, str], stocked: None) -> None:
        """A tool with no description is a tool a model guesses at, and this surface's
        whole safety argument lives in what the descriptions say."""
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()

        for tool in listed.tools:
            assert tool.description, f"{tool.name} has no description"

    async def test_nothing_destructive_is_offered(
        self, cook: dict[str, str], stocked: None
    ) -> None:
        """Reads freely, additive writes yes, irreversible writes no. An agent acting on a
        misheard instruction should not be able to throw away a week's plan or a cook's
        stock — MCP gives the server no say in whether the host asks first (ADR-068)."""
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()

        offered = {tool.name for tool in listed.tools}
        for forbidden in ("delete_plan", "record_waste", "consume_stock", "merge_foods"):
            assert forbidden not in offered


class TestWritingOneDown:
    """The half of the scenario that is new.

    An agent that has looked up its ingredients writes the recipe and this stores it. What
    makes that safe is not a rule in the tool: it is that a recipe line takes an
    `ingredient_id` and has never taken a name, so there is no way for a model to invent a
    food on the way past — and the verdict is computed from the entries it picked, exactly
    as for a recipe generated here (ADR-006, ADR-047).
    """

    async def written(self, flour: int) -> dict[str, Any]:
        return {
            "title": "Focaccia",
            "summary": "Slow, and mostly waiting.",
            "yield_magnitude": "1",
            "yield_unit": "piece",
            "lines": [{"ingredient_id": flour, "magnitude": "500", "unit": "g"}],
            "steps": [{"instruction": "Mix, rest, dimple, bake."}],
        }

    async def food(self, named: str, headers: dict[str, str]) -> int:
        async with talking(headers) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            answer = await session.call_tool("find_a_food", {"named": named})
        found = answer.structured_content or {}
        return int(found["result"][0]["ingredient_id"])

    async def test_a_recipe_an_agent_wrote_is_kept(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        flour = await self.food("plain flour", cook)

        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            answer = await session.call_tool("write_a_recipe", await self.written(flour))

        assert not answer.is_error, answer.content
        listed = (await client.get("/api/v1/recipes", headers=cook)).json()
        assert [one["title"] for one in listed] == ["Focaccia"]

    async def test_it_is_recorded_as_generated_rather_than_authored(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """A cook looking at their own collection should be able to tell what they wrote
        from what something wrote for them."""
        flour = await self.food("plain flour", cook)
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("write_a_recipe", await self.written(flour))

        listed = (await client.get("/api/v1/recipes", headers=cook)).json()
        found = await client.get(f"/api/v1/recipes/{listed[0]['id']}", headers=cook)
        assert found.json()["provenance"] == "generated"

    async def test_a_food_that_is_not_in_the_registry_cannot_be_written(
        self, cook: dict[str, str], stocked: None
    ) -> None:
        """The whole consistency argument in one assertion. There is no way to spell an
        ingredient into a recipe: a line names an id, so an agent that has not looked the
        food up cannot write about it at all — and nobody has to merge anything later."""
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            answer = await session.call_tool(
                "write_a_recipe",
                {
                    "title": "Something",
                    "yield_magnitude": "1",
                    "yield_unit": "piece",
                    "lines": [{"ingredient_id": 9999, "magnitude": "1", "unit": "g"}],
                    "steps": [{"instruction": "Do it."}],
                },
            )
        assert answer.is_error
        said = " ".join(one.text for one in answer.content if hasattr(one, "text"))
        assert "find_a_food" in said

    async def test_a_recipe_the_household_cannot_eat_is_refused(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """Stricter than importing, on purpose: an imported recipe exists in the world
        whatever it contains, and this one was written on these people's behalf. The
        verdict is computed from the entries the agent picked, not from anything it said
        (ADR-006, ADR-047)."""
        await registry.classify("tomato", frozenset())
        await registry.register(
            slug="butter",
            kind=IngredientKind.SOLID,
            density=None,
            names={"en-GB": ["butter"]},
            origin=Origin.SEED,
        )
        await registry.classify("butter", frozenset({Allergen.MILK}))
        await client.post(
            "/api/v1/eaters",
            json={
                "name": "Nadia",
                "age_band": "adult",
                "constraints": [
                    {"allergen": "milk", "ingredient_slug": None, "severity": "medical"}
                ],
            },
            headers=cook,
        )
        butter = await self.food("butter", cook)

        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            answer = await session.call_tool(
                "write_a_recipe",
                {
                    "title": "Buttered anything",
                    "yield_magnitude": "1",
                    "yield_unit": "piece",
                    "lines": [{"ingredient_id": butter, "magnitude": "50", "unit": "g"}],
                    "steps": [{"instruction": "Butter it."}],
                },
            )

        assert answer.is_error
        # And the reason travels. An agent told only "that failed" will guess at why, and
        # guessing at why a recipe is unsuitable is the thing to prevent — so the refusal
        # is a `ToolError`, whose message reaches the model, rather than a crash, whose
        # does not.
        said = " ".join(one.text for one in answer.content if hasattr(one, "text"))
        assert "cannot eat it" in said
        assert "milk" in said

        assert (await client.get("/api/v1/recipes", headers=cook)).json() == []


class TestWhatCanBeReadRatherThanCalled:
    """Academy pages as MCP resources.

    A tool call is a question asked and answered; a resource is a thing with an address
    that a host can hold on to and hand to a model as context. An Academy page is the
    second: it is prose written to be read by somebody who does not know a word, it does
    not change between one question and the next, and its address is its slug.

    Tools stay too — `what_does_this_word_mean` answers "which page is this word", which is
    a question and not an address (ADR-058).
    """

    @pytest.fixture
    async def explained(self) -> None:
        from quookly.contracts.academy import NewPage, PageKind, Wording

        await academy.store_many(
            [
                NewPage(
                    slug="blanch",
                    kind=PageKind.TECHNIQUE,
                    wordings={
                        "en-GB": Wording(
                            name="blanch",
                            spellings=["blanched"],
                            summary="Into boiling water, briefly.",
                            explanation="Boil, then stop it cooking in iced water.",
                        )
                    },
                )
            ],
            # Seeded pages arrive read: nobody signs off what the instance shipped.
            origin=Origin.SEED,
        )

    async def test_a_page_has_an_address(self, cook: dict[str, str], explained: None) -> None:
        """A template rather than one resource per page. Which pages exist is a question —
        `what_words_does_this_kitchen_explain` answers it — and a client that pulled five
        hundred Academy pages into its resource list would be holding a book to look up a
        word."""
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_resource_templates()

        assert "quookly://academy/{slug}" in {one.uri_template for one in listed.resource_templates}

    async def test_a_page_reads_as_prose(self, cook: dict[str, str], explained: None) -> None:
        """Prose rather than a JSON blob. What a resource is for is being read."""
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            page = await session.read_resource("quookly://academy/blanch")

        said = "".join(getattr(one, "text", "") for one in page.contents)
        assert "Into boiling water" in said
        assert "iced water" in said

    async def test_a_page_nobody_has_read_is_not_published(
        self, cook: dict[str, str], explained: None
    ) -> None:
        """The same rule the Academy itself follows. A resource is fetched by the *host*
        and carries no token, so what is behind this address is what a stranger may
        already read — and an unreviewed page is not that (ADR-060, ADR-063)."""
        from quookly.contracts.academy import NewPage, PageKind, Wording

        await academy.store_many(
            [
                NewPage(
                    slug="spatchcock",
                    kind=PageKind.TECHNIQUE,
                    wordings={
                        "en-GB": Wording(
                            name="spatchcock",
                            spellings=[],
                            summary="Flatten a bird.",
                            explanation="Cut out the backbone.",
                        )
                    },
                )
            ],
            # A cook's page, which nobody here has read yet.
            origin=Origin.USER,
        )

        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            with pytest.raises(Exception, match="published"):
                await session.read_resource("quookly://academy/spatchcock")


class TestWhatAnAgentIsAskedToDo:
    """Prompts: the questions worth having a name for.

    Not instructions to the model about safety — those belong in the server's own
    instructions, where they apply to every call rather than to the one somebody chose a
    prompt for.
    """

    async def test_the_prompts_are_listed(self, cook: dict[str, str], stocked: None) -> None:
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_prompts()

        assert "whats_for_dinner" in {one.name for one in listed.prompts}

    async def test_dinner_asks_the_kitchen_before_it_asks_the_model(
        self, cook: dict[str, str], stocked: None
    ) -> None:
        """A prompt that only said "suggest dinner" would be a prompt with no kitchen in
        it. This one tells the model where to look first, which is the whole difference
        between an assistant and a search engine with opinions."""
        async with talking(cook) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            asked = await session.get_prompt("whats_for_dinner", {"occasion": "a game on"})

        said = " ".join(getattr(one.content, "text", "") for one in asked.messages)
        assert "a game on" in said
        assert "what_needs_using_soon" in said
        assert "what_could_i_cook" in said
