"""Publish and subscribe (ADR-002's escape hatch, made real).

The bus is what makes the Manager-must-not-call-Manager rule survivable rather than
merely enforced. These tests are about the two properties that decide whether it is safe
to build accounting on: a fact reaches every listener, and a listener that fails is not
quietly swallowed.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from quookly.contracts.events import Event, MealCooked
from quookly.utilities import events


@dataclass(frozen=True, slots=True)
class SomethingElse(Event):
    what: str


@pytest.fixture(autouse=True)
def a_clean_bus() -> None:
    events.forget_everything()


def cooked() -> MealCooked:
    return MealCooked(cook_id=1, plan_slot_id=7, at=datetime(2026, 8, 24, tzinfo=UTC))


async def test_a_listener_hears_the_fact_it_asked_for() -> None:
    heard: list[MealCooked] = []
    events.subscribe(MealCooked, lambda fact: _record(heard, fact))

    await events.publish(cooked())

    assert [fact.plan_slot_id for fact in heard] == [7]


async def test_a_listener_hears_nothing_else() -> None:
    """A publisher states what happened; it does not address anybody."""
    heard: list[Event] = []
    events.subscribe(MealCooked, lambda fact: _record(heard, fact))

    await events.publish(SomethingElse(what="a recipe was published"))

    assert heard == []


async def test_a_fact_nobody_listens_to_is_not_a_problem() -> None:
    """Most facts are worth stating before anybody wants them, and a published fact with
    no listener is how a feature arrives later without a migration."""
    await events.publish(cooked())


async def test_all_of_them_hear_it() -> None:
    first: list[Event] = []
    second: list[Event] = []
    events.subscribe(MealCooked, lambda fact: _record(first, fact))
    events.subscribe(MealCooked, lambda fact: _record(second, fact))

    await events.publish(cooked())

    assert len(first) == len(second) == 1


async def test_publishing_waits_for_the_listeners() -> None:
    """Awaited rather than fired and forgotten. A meal cooked whose stock was never
    consumed is stock reserved forever, and the publisher has to be able to tell."""
    finished: list[str] = []

    async def slow(_: Event) -> None:
        finished.append("listener")

    events.subscribe(MealCooked, slow)
    await events.publish(cooked())
    finished.append("publish returned")

    assert finished == ["listener", "publish returned"]


async def test_a_failing_listener_is_not_swallowed() -> None:
    """The publisher does not learn who failed — only that the fact could not be fully
    acted on, which is enough for it to refuse to pretend otherwise."""

    async def refuses(_: Event) -> None:
        raise RuntimeError("the pantry said no")

    events.subscribe(MealCooked, refuses)

    with pytest.raises(RuntimeError, match="the pantry said no"):
        await events.publish(cooked())


async def _record(into: list, fact: Event) -> None:  # type: ignore[type-arg]
    into.append(fact)
