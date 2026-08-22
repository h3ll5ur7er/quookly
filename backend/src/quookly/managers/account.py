"""Getting into an instance: bootstrap, applying, being let in, signing in.

Sequences the steps; the rules live elsewhere. Password shape is enforced by the
`Registration` contract, hashing and token issue by the `Security` utility, and storage
by `CookAccess`.

Anybody may **apply** to an instance; an administrator decides
([ADR-049](../../../doc/07-decisions.md)). A self-hosted Quookly is somebody's household
server, so open registration is wrong and an invite-only wall that gives a visitor nowhere
to go is unfriendly. Applying is the middle: the door has a bell.
"""

from quookly.access import cook as cook_access
from quookly.contracts.accounts import Authenticated, Credentials, Registration
from quookly.contracts.cook import Cook, Standing
from quookly.contracts.errors import (
    BootstrapClosed,
    InvalidCredentials,
    NotYetApproved,
    Refused,
)
from quookly.utilities.security import hash_password, issue_token, verify_password

# Verified against when no account matches, so that a missing account and a wrong
# password cost the same time. Without it, response latency reveals which emails exist.
_ABSENT_ACCOUNT_HASH = hash_password("no account matches this password")


def _authenticated(cook: Cook) -> Authenticated:
    return Authenticated(token=issue_token(cook_id=cook.id, is_admin=cook.is_admin), cook=cook)


async def bootstrap_required() -> bool:
    """Whether the instance still has no account at all (FR-16)."""
    return not await cook_access.any_registered()


async def bootstrap_admin(registration: Registration) -> Authenticated:
    """Create the first account, as an admin.

    Closed by the existence of *any* account, not just an admin one — otherwise an
    instance someone had already registered on could still be claimed.
    """
    if not await bootstrap_required():
        raise BootstrapClosed
    cook = await cook_access.register(
        registration.email,
        registration.display_name,
        hash_password(registration.password),
        is_admin=True,
        # The person claiming the instance is the one who would do the approving.
        standing=Standing.APPROVED,
    )
    return _authenticated(cook)


async def apply(registration: Registration) -> Cook:
    """Ask to be let in (UC-10.6).

    No token comes back, and that is the point: an application is not an account yet. The
    password is hashed and kept now rather than asked for again on approval, so that being
    let in is one message to read rather than a second form to fill in.
    """
    return await cook_access.register(
        registration.email,
        registration.display_name,
        hash_password(registration.password),
        standing=Standing.APPLIED,
    )


async def applicants() -> list[Cook]:
    """Who is waiting, oldest first (UC-10.6)."""
    return await cook_access.applicants()


async def decide(cook_id: int, *, approved: bool) -> Cook | None:
    """Let an applicant in, or turn them away (UC-10.6).

    Deciding again is allowed and says so plainly: an admin who refused somebody by
    mistake can approve them, and one who approved a stranger can shut the door. What
    cannot be undone is what the account did while it was open, which is the pantry's and
    the plan's business rather than this manager's.
    """
    return await cook_access.decide(cook_id, Standing.APPROVED if approved else Standing.REFUSED)


async def sign_in(credentials: Credentials) -> Authenticated:
    """Exchange credentials for a token, or raise `InvalidCredentials`."""
    credential = await cook_access.fetch_credential(credentials.email)
    stored_hash = credential.password_hash if credential else _ABSENT_ACCOUNT_HASH
    matched = verify_password(credentials.password, stored_hash)

    if credential is None or not matched:
        raise InvalidCredentials

    cook = await cook_access.fetch_by_email(credentials.email)
    if cook is None:
        raise InvalidCredentials

    # Only asked once the password has matched. Somebody who knows the password already
    # knows the account exists, so saying which of the two states it is in tells them
    # nothing they could not already see — and saying nothing would leave an applicant
    # retyping a password that was right all along.
    if cook.standing is Standing.APPLIED:
        raise NotYetApproved
    if cook.standing is Standing.REFUSED:
        raise Refused

    return _authenticated(cook)


async def fetch(cook_id: int) -> Cook | None:
    """The account behind a token."""
    return await cook_access.fetch(cook_id)
