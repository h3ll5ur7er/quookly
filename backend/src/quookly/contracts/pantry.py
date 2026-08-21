"""What is in the kitchen, and what left it without being eaten.

Stock is held as **lots**, not as a running total per ingredient. Two kilos of flour
bought a month apart are two different things the moment one of them has a date on it,
and an expiry warning is only worth something if it names the packet that is about to go
off rather than the ingredient in general.

Waste is recorded as its own fact rather than inferred from stock going down. The product
exists partly to reduce waste (V9, UC-5.4), and a number that is only ever a subtraction
cannot answer "what did we throw away, and why".
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import DecimalString, Quantity


class WasteReason(Enum):
    """Why food left the kitchen without being eaten.

    `SPOILED` and `EXPIRED` are kept apart deliberately, and they are the whole point of
    asking. Food that actually went off was bought or stored badly; food binned on its
    date was very often still fine, and that is the waste a cook can most easily stop.
    Collapsing the two into "off" throws away the only distinction worth acting on.
    """

    SPOILED = "spoiled"
    EXPIRED = "expired"
    UNEATEN = "uneaten"
    DAMAGED = "damaged"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class StockItem:
    """One lot: some of an ingredient, arrived at one time, with one date on it.

    `expires_on` is a date rather than an instant. Nothing in a kitchen expires at 14:32,
    and a timestamp would invite a timezone question that has no correct answer for a
    carton of milk.
    """

    id: int
    cook_id: int
    ingredient_id: int
    quantity: Quantity
    expires_on: date | None
    note: str | None
    received_at: datetime


@dataclass(frozen=True, slots=True)
class WasteRecord:
    """Something thrown away, and why.

    Carries the ingredient itself rather than only a reference to the lot, so the record
    still reads after the lot it came from is long empty.
    """

    id: int
    cook_id: int
    ingredient_id: int
    quantity: Quantity
    reason: WasteReason
    note: str | None
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class Reservation:
    """Some of one lot, held aside for one planned meal (ADR-004).

    Against a lot rather than against an ingredient, so a plan can hold the carton that
    goes off on Thursday rather than "some milk" — which is the reservation worth making
    if the point is to eat food before it spoils.

    The row exists exactly while the claim is held. Releasing deletes it and cooking
    deletes it, so there is no status to read and no way for a stale one to keep stock
    invisible (ADR-036).
    """

    id: int
    stock_item_id: int
    plan_slot_id: int
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class Availability:
    """One lot, and how much of it nothing has claimed yet.

    `free` is computed from the reservations, never stored. A `reserved` column beside the
    quantity would be a second source of truth about the same butter, and the two would
    disagree the first time anything went wrong halfway through.
    """

    lot: StockItem
    free: Quantity


@dataclass(frozen=True, slots=True)
class Released:
    """A claim that had to give way, and the meal that was counting on it."""

    plan_slot_id: int
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class Adjusted:
    """A lot after a cook has said what is really there, and what that cost.

    The fridge is the authority. If a cook reports less than a plan has claimed, the plan
    is wrong rather than the cook — so the excess claims are let go and named here, and
    the caller can say which meal now needs shopping for.
    """

    lot: StockItem
    released: list[Released]


# What crosses the API.


class Freshness(Enum):
    """How urgently a lot wants using, coarsely.

    A band rather than a number, because this drives colour and ordering. The precise
    count of days travels beside it, so the interface can say "in two days" without this
    enum needing a case for every number.
    """

    UNDATED = "undated"
    FRESH = "fresh"
    SOON = "soon"
    PAST = "past"


class StockLotView(BaseModel):
    """One lot as a client reads it."""

    model_config = ConfigDict(frozen=True)

    id: int
    magnitude: str
    # The unit's symbol — "g", "cup (US)" — as everywhere else on the wire. A cook reads
    # symbols, and a client that has to translate an enum name into one will disagree
    # with the server about at least one of them.
    unit: str
    quantity: str
    expires_on: date | None
    # Negative once the date has passed, so "3 days ago" and "in 3 days" are the same
    # field read two ways. Absent when the lot carries no date at all.
    days_remaining: int | None
    freshness: Freshness
    note: str | None


class PantryEntry(BaseModel):
    """Everything the cook has of one ingredient, lot by lot.

    `total` is absent when the lots cannot honestly be added up — a jar and 200 g of the
    same thing have no sum. Absent rather than approximated: the lots are all listed
    anyway, so nothing is hidden by declining to invent a number.
    """

    model_config = ConfigDict(frozen=True)

    ingredient_id: int
    slug: str
    name: str
    kind: IngredientKind
    total: str | None
    # The most urgent band across the lots, so a card can be marked without the client
    # re-deriving a rule that lives on the server.
    freshness: Freshness
    lots: list[StockLotView]


class ReceiveInput(BaseModel):
    """Stock arriving (UC-5.1)."""

    model_config = ConfigDict(frozen=True)

    ingredient_id: int
    magnitude: DecimalString = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    expires_on: date | None = None
    note: str | None = Field(default=None, max_length=200)


class AdjustInput(BaseModel):
    """What is actually there now (UC-5.3).

    A restatement, not a difference. A cook looking into a jar knows how much is in it,
    not how much has gone since they last looked, and a difference sent twice by a flaky
    connection subtracts twice.

    In the lot's own unit — the one it is displayed in. There is no form in which a cook
    reads a quantity in grams and types one in kilos.
    """

    model_config = ConfigDict(frozen=True)

    magnitude: DecimalString = Field(ge=0)


class WasteInput(BaseModel):
    """Something thrown away (UC-5.4). The magnitude is in the lot's own unit."""

    model_config = ConfigDict(frozen=True)

    magnitude: DecimalString = Field(gt=0)
    reason: WasteReason
    note: str | None = Field(default=None, max_length=200)
