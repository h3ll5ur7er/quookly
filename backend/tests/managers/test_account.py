"""Getting into an instance: bootstrap, registration, sign-in.

The bootstrap is the one-time path that gives a fresh instance its first admin. It
closes permanently once any account exists (FR-16).
"""

from collections.abc import AsyncIterator

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.accounts import Credentials, Registration
from quookly.contracts.errors import (
    BootstrapClosed,
    EmailAlreadyRegistered,
    InvalidCredentials,
)
from quookly.managers import account as account_manager
from quookly.utilities.configuration import get_settings
from quookly.utilities.security import read_token, verify_password

PASSWORD = "a-sufficiently-long-password"


def registration(email: str = "cook@example.com") -> Registration:
    return Registration(email=email, display_name="Emanuel", password=PASSWORD)


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


class TestBootstrap:
    async def test_a_fresh_instance_needs_bootstrapping(self) -> None:
        assert await account_manager.bootstrap_required() is True

    async def test_the_first_account_is_an_admin(self) -> None:
        authenticated = await account_manager.bootstrap_admin(registration())
        assert authenticated.cook.is_admin is True

    async def test_the_bootstrap_closes_once_an_account_exists(self) -> None:
        await account_manager.bootstrap_admin(registration())
        assert await account_manager.bootstrap_required() is False

    async def test_bootstrapping_twice_is_refused(self) -> None:
        await account_manager.bootstrap_admin(registration())
        with pytest.raises(BootstrapClosed):
            await account_manager.bootstrap_admin(registration("second@example.com"))

    async def test_the_bootstrap_closes_against_any_account_not_just_admins(self) -> None:
        """Otherwise an open instance could be claimed by whoever asks first."""
        await account_manager.register(registration())
        with pytest.raises(BootstrapClosed):
            await account_manager.bootstrap_admin(registration("admin@example.com"))


class TestRegistration:
    async def test_registration_returns_a_usable_token(self) -> None:
        authenticated = await account_manager.register(registration())
        principal = read_token(authenticated.token)
        assert principal is not None
        assert principal.cook_id == authenticated.cook.id

    async def test_an_ordinary_registration_is_not_an_admin(self) -> None:
        authenticated = await account_manager.register(registration())
        assert authenticated.cook.is_admin is False

    async def test_the_password_is_stored_hashed(self) -> None:
        await account_manager.register(registration())
        credential = await cook_access.fetch_credential("cook@example.com")
        assert credential is not None
        assert credential.password_hash != PASSWORD
        assert verify_password(PASSWORD, credential.password_hash)

    async def test_a_duplicate_email_is_refused(self) -> None:
        await account_manager.register(registration())
        with pytest.raises(EmailAlreadyRegistered):
            await account_manager.register(registration())


class TestSignIn:
    async def test_correct_credentials_are_accepted(self) -> None:
        await account_manager.register(registration())
        authenticated = await account_manager.sign_in(
            Credentials(email="cook@example.com", password=PASSWORD)
        )
        assert authenticated.cook.email == "cook@example.com"

    async def test_a_wrong_password_is_refused(self) -> None:
        await account_manager.register(registration())
        with pytest.raises(InvalidCredentials):
            await account_manager.sign_in(
                Credentials(email="cook@example.com", password="wrong-password-entirely")
            )

    async def test_an_unknown_email_fails_the_same_way_as_a_wrong_password(self) -> None:
        """Distinguishable failures tell an attacker which emails hold accounts."""
        await account_manager.register(registration())
        with pytest.raises(InvalidCredentials) as unknown:
            await account_manager.sign_in(
                Credentials(email="nobody@example.com", password=PASSWORD)
            )
        with pytest.raises(InvalidCredentials) as wrong:
            await account_manager.sign_in(
                Credentials(email="cook@example.com", password="wrong-password-entirely")
            )
        assert str(unknown.value) == str(wrong.value)

    async def test_sign_in_normalises_the_email(self) -> None:
        await account_manager.register(registration())
        authenticated = await account_manager.sign_in(
            Credentials(email="  COOK@Example.com ", password=PASSWORD)
        )
        assert authenticated.cook.email == "cook@example.com"
