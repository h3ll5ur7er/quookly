"""Password hashing and bearer tokens.

Passwords are hashed with Argon2 via pwdlib; tokens are signed with PyJWT. Both choices
are the currently maintained ones — passlib and python-jose are effectively abandoned,
which is disqualifying for security code.

Every verification path returns a value rather than raising. A malformed hash or a
forged token is an expected input to a public endpoint, not an exceptional condition.
"""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from quookly.contracts.security import Principal
from quookly.utilities.configuration import get_settings

ALGORITHM = "HS256"

_hasher = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    """Hash a password for storage. Salted, so equal passwords hash differently."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Whether the password matches the stored hash.

    A corrupt or empty hash fails the check rather than raising: a bad row must cost one
    login, not the endpoint.
    """
    if not hashed:
        return False
    try:
        return _hasher.verify(plain, hashed)
    except Exception:
        return False


def issue_token(*, cook_id: int, is_admin: bool, lifetime: timedelta | None = None) -> str:
    """Issue a bearer token for a cook.

    Tokens cannot be revoked before they expire — there is no token store yet — so the
    lifetime is the only bound on a leaked one. See the note in the development docs.
    """
    settings = get_settings()
    window = lifetime if lifetime is not None else timedelta(hours=settings.token_lifetime_hours)
    issued_at = datetime.now(UTC)
    claims = {
        "sub": str(cook_id),
        "admin": is_admin,
        "iat": issued_at,
        "exp": issued_at + window,
    }
    return jwt.encode(claims, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def read_token(token: str) -> Principal | None:
    """The principal a token attests to, or None if it attests to nothing we trust.

    The algorithm is pinned, so a token declaring `alg: none` — or any algorithm other
    than the one we sign with — is rejected before its claims are read.
    """
    try:
        claims = jwt.decode(
            token,
            get_settings().secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.InvalidTokenError:
        return None

    try:
        cook_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    return Principal(cook_id=cook_id, is_admin=bool(claims.get("admin", False)))
