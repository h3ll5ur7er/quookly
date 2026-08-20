"""The people a cook cooks for, as stored (UC-6.3, UC-6.4, UC-6.5).

An eater is not an account (ADR-005), so these rows hang off a cook rather than off a
login. The tests below are mostly about two things that go quietly wrong: a constraint
outliving the edit that removed it, and an appetite multiplier that does not sum exactly.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import eater as eater_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.eater import AgeBand, Constraint, Severity
from quookly.contracts.ingredient import Allergen
from quookly.utilities.configuration import get_settings


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def cook_id() -> int:
    cook = await cook_access.register("chef@example.com", "Emanuel", "hash")
    return cook.id


@pytest.fixture
async def other_cook_id() -> int:
    cook = await cook_access.register("neighbour@example.com", "Someone", "hash")
    return cook.id


PEANUT = Constraint(allergen=Allergen.PEANUTS, ingredient_slug=None, severity=Severity.MEDICAL)
CORIANDER = Constraint(
    allergen=None, ingredient_slug="coriander-leaf", severity=Severity.PREFERENCE
)


class TestRecording:
    async def test_an_eater_is_read_back_whole(self, cook_id: int) -> None:
        added = await eater_access.add(
            cook_id=cook_id, name="Mira", age_band=AgeBand.CHILD, appetite=Decimal("0.6")
        )
        fetched = await eater_access.fetch(added.id)
        assert fetched is not None
        assert fetched.name == "Mira"
        assert fetched.age_band is AgeBand.CHILD
        assert fetched.appetite == Decimal("0.6")
        assert fetched.cook_id == cook_id

    async def test_appetite_defaults_to_a_standard_portion(self, cook_id: int) -> None:
        added = await eater_access.add(cook_id=cook_id, name="Ana", age_band=AgeBand.ADULT)
        assert added.appetite == Decimal("1")

    async def test_an_eater_starts_with_no_constraints(self, cook_id: int) -> None:
        added = await eater_access.add(cook_id=cook_id, name="Ana", age_band=AgeBand.ADULT)
        assert added.constraints == []

    async def test_fetching_something_that_is_not_there_is_not_an_error(self) -> None:
        assert await eater_access.fetch(404) is None


class TestConstraints:
    async def test_an_allergen_constraint_survives_the_round_trip(self, cook_id: int) -> None:
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        fetched = await eater_access.fetch(added.id)
        assert fetched is not None
        assert fetched.constraints == [PEANUT]

    async def test_severity_survives_the_round_trip(self, cook_id: int) -> None:
        """A medical constraint read back as a preference is the failure this guards."""
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        fetched = await eater_access.fetch(added.id)
        assert fetched is not None
        assert fetched.constraints[0].severity is Severity.MEDICAL

    async def test_an_ingredient_constraint_survives_the_round_trip(self, cook_id: int) -> None:
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[CORIANDER]
        )
        fetched = await eater_access.fetch(added.id)
        assert fetched is not None
        assert fetched.constraints == [CORIANDER]

    async def test_an_ingredient_constraint_need_not_be_in_the_registry(self, cook_id: int) -> None:
        """Somebody's avoidance does not wait on a registry entry existing for it."""
        added = await eater_access.add(
            cook_id=cook_id,
            name="Jonas",
            age_band=AgeBand.ADULT,
            constraints=[
                Constraint(allergen=None, ingredient_slug="nothing-here", severity=Severity.MEDICAL)
            ],
        )
        assert added.constraints[0].ingredient_slug == "nothing-here"

    async def test_the_same_constraint_twice_is_stored_once(self, cook_id: int) -> None:
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT, PEANUT]
        )
        assert added.constraints == [PEANUT]

    async def test_two_severities_for_one_allergen_are_both_kept(self, cook_id: int) -> None:
        """Contradictions are for a judge to resolve, not for storage to silently drop."""
        milder = Constraint(
            allergen=Allergen.PEANUTS, ingredient_slug=None, severity=Severity.PREFERENCE
        )
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT, milder]
        )
        assert len(added.constraints) == 2


class TestAppetite:
    async def test_multipliers_sum_exactly(self, cook_id: int) -> None:
        """0.3 + 1.4 + 0.6 must be 2.3, not 2.3000000000000003 (domain model)."""
        for name, appetite in (("Toddler", "0.3"), ("Teen", "1.4"), ("Nonna", "0.6")):
            await eater_access.add(
                cook_id=cook_id,
                name=name,
                age_band=AgeBand.ADULT,
                appetite=Decimal(appetite),
            )
        household = await eater_access.list_for_cook(cook_id)
        assert sum(eater.appetite for eater in household) == Decimal("2.3")

    async def test_an_appetite_of_nothing_is_refused(self, cook_id: int) -> None:
        """Somebody who eats nothing is not at the table, and would drag the yield down."""
        with pytest.raises(ValueError):
            await eater_access.add(
                cook_id=cook_id, name="Ghost", age_band=AgeBand.ADULT, appetite=Decimal("0")
            )

    async def test_a_negative_appetite_is_refused(self, cook_id: int) -> None:
        with pytest.raises(ValueError):
            await eater_access.add(
                cook_id=cook_id, name="Ghost", age_band=AgeBand.ADULT, appetite=Decimal("-1")
            )

    async def test_more_precision_than_is_stored_is_rounded_on_the_way_in(
        self, cook_id: int
    ) -> None:
        """So the value read back is the value stored, rather than the column deciding."""
        added = await eater_access.add(
            cook_id=cook_id, name="Ana", age_band=AgeBand.ADULT, appetite=Decimal("1.333")
        )
        assert added.appetite == Decimal("1.33")
        fetched = await eater_access.fetch(added.id)
        assert fetched is not None
        assert fetched.appetite == added.appetite


class TestHouseholds:
    async def test_a_household_lists_in_the_order_it_was_built(self, cook_id: int) -> None:
        for name in ("Ana", "Jonas", "Mira"):
            await eater_access.add(cook_id=cook_id, name=name, age_band=AgeBand.ADULT)
        household = await eater_access.list_for_cook(cook_id)
        assert [eater.name for eater in household] == ["Ana", "Jonas", "Mira"]

    async def test_households_do_not_mix(self, cook_id: int, other_cook_id: int) -> None:
        await eater_access.add(cook_id=cook_id, name="Mira", age_band=AgeBand.CHILD)
        assert await eater_access.list_for_cook(other_cook_id) == []

    async def test_listing_carries_constraints(self, cook_id: int) -> None:
        """A household read without constraints would be judged as though nobody had any."""
        await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        household = await eater_access.list_for_cook(cook_id)
        assert household[0].constraints == [PEANUT]

    async def test_constraints_stay_with_their_own_eater(self, cook_id: int) -> None:
        await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        await eater_access.add(cook_id=cook_id, name="Ana", age_band=AgeBand.ADULT)
        household = await eater_access.list_for_cook(cook_id)
        assert household[1].constraints == []


class TestGathering:
    async def test_the_named_eaters_come_back(self, cook_id: int) -> None:
        ana = await eater_access.add(cook_id=cook_id, name="Ana", age_band=AgeBand.ADULT)
        await eater_access.add(cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT)
        mira = await eater_access.add(cook_id=cook_id, name="Mira", age_band=AgeBand.CHILD)
        gathered = await eater_access.for_ids([ana.id, mira.id], cook_id)
        assert [eater.name for eater in gathered] == ["Ana", "Mira"]

    async def test_another_cooks_eater_is_not_gathered(
        self, cook_id: int, other_cook_id: int
    ) -> None:
        """Asking for an id that is not yours returns nothing rather than someone's allergies."""
        theirs = await eater_access.add(
            cook_id=other_cook_id, name="Stranger", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        assert await eater_access.for_ids([theirs.id], cook_id) == []

    async def test_gathering_nobody_is_not_an_error(self, cook_id: int) -> None:
        assert await eater_access.for_ids([], cook_id) == []


class TestAmending:
    async def test_a_rename_keeps_the_constraints(self, cook_id: int) -> None:
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        amended = await eater_access.amend(added.id, name="Jonas Meier")
        assert amended is not None
        assert amended.name == "Jonas Meier"
        assert amended.constraints == [PEANUT]

    async def test_appetite_can_be_corrected(self, cook_id: int) -> None:
        added = await eater_access.add(cook_id=cook_id, name="Mira", age_band=AgeBand.CHILD)
        amended = await eater_access.amend(added.id, appetite=Decimal("0.5"))
        assert amended is not None
        assert amended.appetite == Decimal("0.5")

    async def test_a_growing_child_changes_age_band(self, cook_id: int) -> None:
        added = await eater_access.add(cook_id=cook_id, name="Mira", age_band=AgeBand.CHILD)
        amended = await eater_access.amend(added.id, age_band=AgeBand.ADULT)
        assert amended is not None
        assert amended.age_band is AgeBand.ADULT

    async def test_amending_nobody_is_not_an_error(self) -> None:
        assert await eater_access.amend(404, name="Nobody") is None


class TestRestating:
    async def test_constraints_are_replaced_wholesale(self, cook_id: int) -> None:
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        restated = await eater_access.restate_constraints(added.id, [CORIANDER])
        assert restated is not None
        assert restated.constraints == [CORIANDER]

    async def test_a_removed_constraint_does_not_linger(self, cook_id: int) -> None:
        """The one that matters: a peanut allergy deleted in the UI must actually go."""
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT, CORIANDER]
        )
        await eater_access.restate_constraints(added.id, [CORIANDER])
        fetched = await eater_access.fetch(added.id)
        assert fetched is not None
        assert PEANUT not in fetched.constraints

    async def test_constraints_can_be_cleared(self, cook_id: int) -> None:
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        restated = await eater_access.restate_constraints(added.id, [])
        assert restated is not None
        assert restated.constraints == []


class TestRemoving:
    async def test_an_eater_can_be_removed(self, cook_id: int) -> None:
        added = await eater_access.add(cook_id=cook_id, name="Mira", age_band=AgeBand.CHILD)
        assert await eater_access.remove(added.id) is True
        assert await eater_access.fetch(added.id) is None

    async def test_removing_takes_the_constraints_with_it(self, cook_id: int) -> None:
        """Orphan constraint rows would attach themselves to the next eater to reuse the id."""
        added = await eater_access.add(
            cook_id=cook_id, name="Jonas", age_band=AgeBand.ADULT, constraints=[PEANUT]
        )
        removed_id = added.id
        await eater_access.remove(removed_id)
        replacement = await eater_access.add(
            cook_id=cook_id, name="Someone Else", age_band=AgeBand.ADULT
        )
        assert replacement.constraints == []

    async def test_removing_leaves_the_rest_of_the_household(self, cook_id: int) -> None:
        added = await eater_access.add(cook_id=cook_id, name="Mira", age_band=AgeBand.CHILD)
        await eater_access.add(cook_id=cook_id, name="Ana", age_band=AgeBand.ADULT)
        await eater_access.remove(added.id)
        assert [eater.name for eater in await eater_access.list_for_cook(cook_id)] == ["Ana"]

    async def test_removing_nobody_says_so(self) -> None:
        assert await eater_access.remove(404) is False
