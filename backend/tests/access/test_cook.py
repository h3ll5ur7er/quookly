"""The cook account: the first persisted entity.

A Cook is an account. An Eater is a person cooked for and is not an account (ADR-005);
the two arrive separately, and this is the former.
"""

from collections.abc import AsyncIterator

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.cook import Cook
from quookly.contracts.errors import EmailAlreadyRegistered
from quookly.utilities.configuration import get_settings

HASH = "not-a-real-hash"


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


class TestRegister:
    async def test_a_registered_cook_can_be_fetched(self) -> None:
        registered = await cook_access.register("cook@example.com", "Emanuel", HASH)
        found = await cook_access.fetch_by_email("cook@example.com")
        assert found == registered

    async def test_registration_returns_a_contract_not_an_orm_row(self) -> None:
        """What leaves the access layer belongs to contracts (ADR-018)."""
        registered = await cook_access.register("cook@example.com", "Emanuel", HASH)
        assert isinstance(registered, Cook)
        assert not isinstance(registered, SQLModel)

    async def test_the_credential_does_not_travel_with_the_cook(self) -> None:
        """A password hash has no business in a value passed around the application."""
        registered = await cook_access.register("cook@example.com", "Emanuel", HASH)
        assert HASH not in repr(registered)
        assert not hasattr(registered, "password_hash")

    async def test_an_email_may_only_be_registered_once(self) -> None:
        await cook_access.register("cook@example.com", "Emanuel", HASH)
        with pytest.raises(EmailAlreadyRegistered):
            await cook_access.register("cook@example.com", "Someone Else", HASH)

    async def test_email_case_and_spacing_do_not_create_a_second_account(self) -> None:
        """Someone typing Mixed@Case at the login form is the same person."""
        await cook_access.register("cook@example.com", "Emanuel", HASH)
        with pytest.raises(EmailAlreadyRegistered):
            await cook_access.register("  Cook@Example.COM  ", "Emanuel", HASH)

    async def test_a_fetch_normalises_the_email_too(self) -> None:
        await cook_access.register("cook@example.com", "Emanuel", HASH)
        assert await cook_access.fetch_by_email("COOK@example.com  ") is not None


class TestFetch:
    async def test_an_unknown_email_is_absent_not_an_error(self) -> None:
        assert await cook_access.fetch_by_email("nobody@example.com") is None


class TestCredential:
    async def test_the_stored_hash_is_retrievable_for_authentication(self) -> None:
        await cook_access.register("cook@example.com", "Emanuel", HASH)
        credential = await cook_access.fetch_credential("cook@example.com")
        assert credential is not None
        assert credential.password_hash == HASH

    async def test_an_unknown_email_has_no_credential(self) -> None:
        assert await cook_access.fetch_credential("nobody@example.com") is None


class TestBootstrap:
    async def test_a_fresh_instance_has_no_cooks(self) -> None:
        """FR-16: the admin bootstrap opens only while this is true."""
        assert await cook_access.any_registered() is False

    async def test_registering_closes_the_bootstrap_window(self) -> None:
        await cook_access.register("cook@example.com", "Emanuel", HASH)
        assert await cook_access.any_registered() is True

    async def test_the_first_cook_may_be_registered_as_an_admin(self) -> None:
        registered = await cook_access.register("admin@example.com", "Emanuel", HASH, is_admin=True)
        assert registered.is_admin is True

    async def test_cooks_are_not_admins_by_default(self) -> None:
        registered = await cook_access.register("cook@example.com", "Emanuel", HASH)
        assert registered.is_admin is False
