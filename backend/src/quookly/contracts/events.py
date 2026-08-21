"""Things that happened.

Facts in the past tense, because that is what an event is. A publisher states what
happened and does not know or care who listens — which is what makes the
Manager-must-not-call-Manager rule survivable rather than merely enforced.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Event:
    """The base every event shares. Carries nothing: a fact's fields are its own."""


@dataclass(frozen=True, slots=True)
class MealCooked(Event):
    """A planned meal was cooked (UC-4.5, FR-19).

    The pantry listens and turns that meal's reservations into consumption. Cooking does
    not need to know how stock accounting is done, and stock accounting does not need to
    know where the meal came from — which is what lets a cooking session (Phase 5) publish
    the same fact without either of them learning about the other.
    """

    cook_id: int
    plan_slot_id: int
    at: datetime
