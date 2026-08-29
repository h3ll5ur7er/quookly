"""A stdio bridge to an instance's MCP surface.

Some hosts launch an MCP server as a subprocess and speak to it over stdin and stdout.
Quookly's surface is mounted in the instance and served over HTTP, because the instance is
on a box somewhere and the agent is on somebody's laptop
([ADR-068](../../../doc/07-decisions.md)). This is what joins the two.

**It is a relay and must stay one.** What crosses is JSON-RPC, unread. The moment it
interprets a message it becomes a second client with its own idea of what the surface is —
which is exactly the thing the decision above rejected. There are no tools here, no
schemas, and nothing to keep in step with the server.

Run it where the agent is:

    BASE_URL=https://kitchen.example quookly-cli mcp

The token comes from `QUOOKLY_TOKEN`, and is the same one the API takes. One token is one
cook.
"""

import os
from collections.abc import AsyncIterator
from typing import Annotated, Any, Protocol

import anyio
import typer
from mcp.client.streamable_http import streamable_http_client
from mcp.server.stdio import stdio_server

from ..di.container import get_container

cli = typer.Typer(no_args_is_help=False)

#: Where the token is read from. An environment variable rather than a flag: a host's
#: configuration file is a place people paste things and then share screenshots of.
TOKEN = "QUOOKLY_TOKEN"


class Reads(Protocol):
    """Something to take messages from.

    A protocol rather than a stream type. The two sides of this bridge are different
    classes — one from the stdio server, one from the HTTP client, and the second lives in
    a private module of the SDK — and what the relay needs from both is the same two
    things. Naming the private class would tie this to an implementation detail of a
    library, to gain nothing.
    """

    def __aiter__(self) -> AsyncIterator[Any]: ...


class Writes(Protocol):
    """Something to put messages into."""

    async def send(self, item: Any) -> None: ...


async def relay(
    from_host: Reads,
    to_host: Writes,
    from_instance: Reads,
    to_instance: Writes,
    stop: anyio.CancelScope,
) -> None:
    """Pump messages both ways until either side goes quiet.

    Either direction ending ends the bridge. A relay that outlived its host would be a
    process nobody launched and nobody stops; one that outlived the instance would be a
    host talking into a socket that is not there.
    """

    async def onwards(reading: Reads, writing: Writes) -> None:
        try:
            async for message in reading:
                await writing.send(message)
        except (anyio.BrokenResourceError, anyio.ClosedResourceError):
            pass
        finally:
            stop.cancel()

    async with anyio.create_task_group() as both:
        both.start_soon(onwards, from_host, to_instance)
        both.start_soon(onwards, from_instance, to_host)


async def _bridged(url: str, token: str | None) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with (
        stdio_server() as (from_host, to_host),
        streamable_http_client(url, http_client=_talking(headers)) as (from_instance, to_instance),
        anyio.create_task_group() as work,
    ):
        await relay(from_host, to_host, from_instance, to_instance, work.cancel_scope)


def _talking(headers: dict[str, str]) -> Any:
    import httpx2

    return httpx2.AsyncClient(headers=headers, follow_redirects=True, timeout=None)


@cli.command()
def serve(
    url: Annotated[
        str | None,
        typer.Option(help="The instance's MCP address. Defaults to BASE_URL plus /mcp."),
    ] = None,
) -> None:
    """Bridge this terminal's stdin and stdout to an instance's MCP surface."""
    where = url or f"{get_container().config.api.base_url().rstrip('/')}/mcp"
    anyio.run(_bridged, where, os.environ.get(TOKEN))
