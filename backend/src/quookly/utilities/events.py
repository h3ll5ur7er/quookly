"""Publish and subscribe, in this process.

The mechanism that makes the Manager-must-not-call-Manager rule survivable. Cooking a
meal has to consume stock, and without a bus `PlanningManager` would call
`PantryManager` — making stock accounting a dependency of planning, and planning a
dependency of every future listener.

A utility, so it depends on no layer. Subscribers register themselves from where the
application is assembled; nothing here knows what a manager is.
"""

from collections.abc import Awaitable, Callable

from quookly.contracts.events import Event
from quookly.utilities.diagnostics import get_logger

Handler = Callable[[Event], Awaitable[None]]

_subscribers: dict[type[Event], list[Handler]] = {}

_log = get_logger("events")


def subscribe[E: Event](event: type[E], handler: Callable[[E], Awaitable[None]]) -> None:
    """Listen for one kind of fact.

    Registration order is the order handlers run in, and it is the only ordering there
    is. A listener that needs to run after another is two facts, not one.
    """
    _subscribers.setdefault(event, []).append(handler)  # type: ignore[arg-type]


async def publish(event: Event) -> None:
    """State that something happened, and let every listener finish before returning.

    **Awaited, and a failure propagates.** Fire-and-forget would make publishing cheap and
    make the consequences invisible: a meal cooked whose stock was never consumed is stock
    reserved forever, which is the failure ADR-004 exists to prevent. The publisher does
    not learn *who* failed — only that the fact could not be fully acted on, which is
    enough for it to refuse to pretend otherwise.

    A failing listener stops the ones after it. With one listener doing real accounting
    that is the safe reading; the day an advisory listener sits beside an essential one —
    points beside stock — is the day this needs splitting, and not before.
    """
    listeners = _subscribers.get(type(event), [])
    if not listeners:
        # Not a problem. Most facts are worth stating before anybody wants them, and a
        # published fact nobody listens to is how a feature arrives without a migration.
        _log.debug("%s published with nobody listening", type(event).__name__)
        return
    for handler in listeners:
        await handler(event)


def forget_everything() -> None:
    """Drop every subscription.

    For tests, which register their own listeners and must not leak them into the next
    one. Nothing in the running application calls this.
    """
    _subscribers.clear()
