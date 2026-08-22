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
from quookly.contracts.cook import Standing
from quookly.contracts.errors import (
    BootstrapClosed,
    EmailAlreadyRegistered,
    InvalidCredentials,
    NotYetApproved,
    Refused,
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
        await account_manager.apply(registration())
        with pytest.raises(BootstrapClosed):
            await account_manager.bootstrap_admin(registration("admin@example.com"))


async def admitted(email: str = "cook@example.com") -> None:
    """An account that applied and was let in — what most of these tests need."""
    applicant = await account_manager.apply(registration(email))
    await account_manager.decide(applicant.id, approved=True)


class TestApplying:
    async def test_applying_does_not_hand_over_a_token(self) -> None:
        """The whole distinction. An endpoint that returned one would be open
        registration wearing a different name."""
        applicant = await account_manager.apply(registration())
        assert not hasattr(applicant, "token")
        assert applicant.standing is Standing.APPLIED

    async def test_an_applicant_is_not_an_admin(self) -> None:
        applicant = await account_manager.apply(registration())
        assert applicant.is_admin is False

    async def test_the_password_is_stored_hashed(self) -> None:
        """Kept at application time rather than asked for again on approval, so being let
        in is a message to read rather than a second form to fill in."""
        await account_manager.apply(registration())
        credential = await cook_access.fetch_credential("cook@example.com")
        assert credential is not None
        assert credential.password_hash != PASSWORD
        assert verify_password(PASSWORD, credential.password_hash)

    async def test_a_duplicate_email_is_refused(self) -> None:
        await account_manager.apply(registration())
        with pytest.raises(EmailAlreadyRegistered):
            await account_manager.apply(registration())

    async def test_applying_twice_is_refused_even_before_a_decision(self) -> None:
        """A second application would give one person two doors, and an admin no way to
        tell which one they were answering."""
        await account_manager.apply(registration())
        with pytest.raises(EmailAlreadyRegistered):
            await account_manager.apply(registration())


class TestBeingLetIn:
    async def test_who_is_waiting(self) -> None:
        await account_manager.apply(registration())
        assert [one.email for one in await account_manager.applicants()] == ["cook@example.com"]

    async def test_the_queue_is_oldest_first(self) -> None:
        """It is a queue somebody works through, and the person waiting longest is the one
        most owed an answer."""
        await account_manager.apply(registration("first@example.com"))
        await account_manager.apply(registration("second@example.com"))
        waiting = [one.email for one in await account_manager.applicants()]
        assert waiting == ["first@example.com", "second@example.com"]

    async def test_somebody_let_in_leaves_the_queue(self) -> None:
        applicant = await account_manager.apply(registration())
        await account_manager.decide(applicant.id, approved=True)
        assert await account_manager.applicants() == []

    async def test_somebody_turned_away_also_leaves_the_queue(self) -> None:
        """Refused is a decision, not a pending one. Leaving them in the queue would ask
        an admin the same question every time they looked."""
        applicant = await account_manager.apply(registration())
        await account_manager.decide(applicant.id, approved=False)
        assert await account_manager.applicants() == []

    async def test_a_refusal_can_be_reconsidered(self) -> None:
        applicant = await account_manager.apply(registration())
        await account_manager.decide(applicant.id, approved=False)
        decided = await account_manager.decide(applicant.id, approved=True)
        assert decided is not None
        assert decided.standing is Standing.APPROVED

    async def test_deciding_about_nobody_is_absent_rather_than_an_error(self) -> None:
        assert await account_manager.decide(9999, approved=True) is None

    async def test_the_first_admin_is_already_in(self) -> None:
        """They are the person who would do the approving."""
        authenticated = await account_manager.bootstrap_admin(registration())
        assert authenticated.cook.standing is Standing.APPROVED

    async def test_being_let_in_returns_a_usable_token_at_sign_in(self) -> None:
        await admitted()
        authenticated = await account_manager.sign_in(
            Credentials(email="cook@example.com", password=PASSWORD)
        )
        principal = read_token(authenticated.token)
        assert principal is not None
        assert principal.cook_id == authenticated.cook.id


class TestSignIn:
    async def test_correct_credentials_are_accepted(self) -> None:
        await admitted()
        authenticated = await account_manager.sign_in(
            Credentials(email="cook@example.com", password=PASSWORD)
        )
        assert authenticated.cook.email == "cook@example.com"

    async def test_a_wrong_password_is_refused(self) -> None:
        await admitted()
        with pytest.raises(InvalidCredentials):
            await account_manager.sign_in(
                Credentials(email="cook@example.com", password="wrong-password-entirely")
            )

    async def test_an_unknown_email_fails_the_same_way_as_a_wrong_password(self) -> None:
        """Distinguishable failures tell an attacker which emails hold accounts."""
        await admitted()
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
        await admitted()
        authenticated = await account_manager.sign_in(
            Credentials(email="  COOK@Example.com ", password=PASSWORD)
        )
        assert authenticated.cook.email == "cook@example.com"


class TestSigningInBeforeBeingLetIn:
    """The credentials are right and the door is not open yet. Told apart from a wrong
    password on purpose: this is only reachable *after* the password matched, so somebody
    who knows it already knows the account exists. What they do not know is that they are
    waiting on a person rather than mistyping."""

    async def test_an_applicant_is_told_they_are_waiting(self) -> None:
        await account_manager.apply(registration())
        with pytest.raises(NotYetApproved):
            await account_manager.sign_in(Credentials(email="cook@example.com", password=PASSWORD))

    async def test_somebody_turned_away_is_told_so(self) -> None:
        """Not "still waiting". That sentence leaves them waiting forever."""
        applicant = await account_manager.apply(registration())
        await account_manager.decide(applicant.id, approved=False)
        with pytest.raises(Refused):
            await account_manager.sign_in(Credentials(email="cook@example.com", password=PASSWORD))

    async def test_a_wrong_password_still_says_nothing(self) -> None:
        """The standing is only revealed once the password has matched. Otherwise this
        endpoint becomes a way to ask which addresses have applied here."""
        await account_manager.apply(registration())
        with pytest.raises(InvalidCredentials):
            await account_manager.sign_in(
                Credentials(email="cook@example.com", password="wrong-password-entirely")
            )
