"""Quookly as tools an agent can use (ADR-068).

A **Client**, the same layer as `routes`: one serves a browser, the other serves an agent,
and both call managers. Mounted in this process rather than reaching the API over HTTP,
because a second process would open the same SQLite file, miss the in-process event bus,
and rebuild the same derived index.

What this surface is for is one evening: somebody is coming over, there is a game on, and
the agent should find something that needs no shopping trip — then write a new recipe out
of what is about to go off. Two things make that work, and neither is new here:

**A recipe line takes an ingredient id, never a name.** So a model writing a recipe through
these tools *cannot invent an ingredient*: it has to look one up and hand back an id. The
mess an import leaves — a second entry for "cherry tomatoes" beside the one for "tomato" —
is not something this has to clean up, because it cannot be made.

**Nothing here decides anything a person would want decided.** Suitability, allergens and
what a quantity comes to are computed where they always were, and these tools carry the
answer rather than the evidence. A model relaying a verdict is fine; a model deriving one
from an ingredient list is the failure ADR-006 exists to prevent, and it is worse here than
on a screen because the model's prose *is* the interface.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.types import Receive, Scope, Send

from quookly.mcp.server import kitchen

__all__ = ["AgentSurface", "agent_app", "kitchen"]


def agent_app() -> Starlette:
    """The MCP surface as an ASGI application, ready to mount.

    A factory rather than a module-level value because each call builds a **new session
    manager**, and a session manager may be run once. The application builds one at
    start-up; a test builds one per test, which is the only way to have more than one
    event loop in a process.

    The path is the root because the caller supplies the prefix by mounting: asking for
    `/mcp` inside a `/mcp` mount serves it at `/mcp/mcp`.

    DNS-rebinding protection is off, deliberately, and it is worth saying why rather than
    leaving a disabled security setting looking like an oversight. It is an allow-list of
    `Host` headers, for a local server a browser could be tricked into calling. It buys
    this instance nothing — the only thing behind these tools is a bearer token, the same
    one the API takes, and a browser tricked into calling a local address does not have
    one. It costs something real: a self-hoster reaches their instance by a name we cannot
    know, so an allow-list would refuse every deployment we failed to guess. This endpoint
    is no more exposed than `/api/v1`, and being stricter here than there would be a
    second, different answer to one question.
    """
    return kitchen.streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


class AgentSurface:
    """The mounted endpoint, and the surface it is currently serving.

    An indirection with one job: **the application can be started more than once in a
    process.** The transport's session manager may be run exactly once, so a lifespan that
    ran one would work the first time and raise the second — which is a strange way for a
    test suite to find out that a web application cannot be restarted, and it is how this
    one found out.

    So the thing that gets mounted is this, which never changes, and each start builds a
    fresh surface behind it. Nothing outside notices.
    """

    def __init__(self) -> None:
        self._serving: Starlette | None = None

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """Build a surface and run its transport for as long as the application does."""
        self._serving = agent_app()
        async with kitchen.session_manager.run():
            try:
                yield
            finally:
                self._serving = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._serving is None:
            raise RuntimeError(
                "The agent surface is not running. It is started by the application's "
                "lifespan, which a bare ASGI transport does not run."
            )
        await self._serving(scope, receive, send)
