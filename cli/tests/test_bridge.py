"""The stdio bridge, which is a relay and nothing else.

A host that speaks only stdio launches this beside itself; the instance is somewhere else
on the network. What crosses is JSON-RPC, unread: the bridge has no opinion about MCP and
must not grow one, because the moment it interprets a message it is a second client with
its own idea of what the surface is (ADR-068).

So what is worth testing is exactly that — a frame goes each way, unchanged.
"""

from typing import Any

import anyio
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCRequest, JSONRPCResponse

from quookly_cli.subcommands.bridge import relay


def asked(request_id: int) -> SessionMessage:
    return SessionMessage(
        JSONRPCRequest(jsonrpc="2.0", id=request_id, method="tools/list", params={})
    )


def answered(request_id: int) -> SessionMessage:
    return SessionMessage(JSONRPCResponse(jsonrpc="2.0", id=request_id, result={"tools": []}))


class Wires:
    """Both sides of the bridge, from the test's point of view.

    `anyio.create_memory_object_stream` hands back **(send, receive)**, and naming those
    two ends after the party at the far end of them rather than after their direction is
    how they got crossed the first time. So: `host_says` is what the test writes as if it
    were the host, `host_hears` is what the test reads as if it were the host, and the two
    the relay is given are their opposites.
    """

    def __init__(self) -> None:
        self.host_says, self._from_host = anyio.create_memory_object_stream[Any](8)
        self._to_host, self.host_hears = anyio.create_memory_object_stream[Any](8)
        self.instance_says, self._from_instance = anyio.create_memory_object_stream[Any](8)
        self._to_instance, self.instance_hears = anyio.create_memory_object_stream[Any](8)

    def start(self, work: anyio.abc.TaskGroup) -> None:
        work.start_soon(
            relay,
            self._from_host,
            self._to_host,
            self._from_instance,
            self._to_instance,
            work.cancel_scope,
        )


async def test_a_question_reaches_the_instance() -> None:
    wires = Wires()
    with anyio.fail_after(2):
        async with anyio.create_task_group() as work:
            wires.start(work)
            await wires.host_says.send(asked(1))

            crossed = await wires.instance_hears.receive()
            assert crossed.message.method == "tools/list"
            assert crossed.message.id == 1
            work.cancel_scope.cancel()


async def test_an_answer_comes_back() -> None:
    wires = Wires()
    with anyio.fail_after(2):
        async with anyio.create_task_group() as work:
            wires.start(work)
            await wires.instance_says.send(answered(7))

            crossed = await wires.host_hears.receive()
            assert crossed.message.id == 7
            assert crossed.message.result == {"tools": []}
            work.cancel_scope.cancel()


async def test_it_reads_nothing_it_relays() -> None:
    """A method this bridge has never heard of crosses unchanged.

    The point of the whole file. A relay that understood MCP would be a second client with
    its own idea of what the surface is, and would need keeping in step with the server —
    which is the thing ADR-068 rejected.
    """
    wires = Wires()
    invented = SessionMessage(
        JSONRPCRequest(jsonrpc="2.0", id=2, method="something/invented/later", params={"x": 1})
    )

    with anyio.fail_after(2):
        async with anyio.create_task_group() as work:
            wires.start(work)
            await wires.host_says.send(invented)

            crossed = await wires.instance_hears.receive()
            assert crossed.message.method == "something/invented/later"
            assert crossed.message.params == {"x": 1}
            work.cancel_scope.cancel()


async def test_a_closed_side_ends_the_bridge() -> None:
    """When the host goes away the bridge goes away. A relay that outlived its host would
    be a process nobody launched and nobody stops."""
    wires = Wires()
    with anyio.fail_after(2):
        async with anyio.create_task_group() as work:
            wires.start(work)
            await wires.host_says.aclose()
