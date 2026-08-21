"""Getting into an instance: bootstrap, registration, sign-in.

Sequences the steps; the rules live elsewhere. Password shape is enforced by the
`Registration` contract, hashing and token issue by the `Security` utility, and storage
by `CookAccess`.
"""

from quookly.access import cook as cook_access
from quookly.contracts.accounts import Authenticated, Credentials, Registration
from quookly.contracts.cook import Cook
from quookly.contracts.errors import BootstrapClosed, InvalidCredentials
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
    )
    return _authenticated(cook)


async def register(registration: Registration) -> Authenticated:
    """Create an ordinary account and sign it in."""
    cook = await cook_access.register(
        registration.email,
        registration.display_name,
        hash_password(registration.password),
    )
    return _authenticated(cook)


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
    return _authenticated(cook)


async def fetch(cook_id: int) -> Cook | None:
    """The account behind a token."""
    return await cook_access.fetch(cook_id)
