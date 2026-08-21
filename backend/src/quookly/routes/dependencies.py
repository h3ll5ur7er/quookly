"""Resolving the caller.

Client-layer plumbing: turns a bearer token into a principal, or refuses. Verification
itself belongs to the `Security` utility; what lives here is the HTTP shape of the
refusal.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from quookly.contracts.security import Principal
from quookly.utilities.security import read_token

_SCHEME = "Bearer"


def current_principal(request: Request) -> Principal:
    """Who is asking, or a 401.

    The challenge header is included so a client is told how to authenticate rather than
    left to guess, and every failure is the same refusal: a token that is missing,
    malformed, expired or forged tells the caller nothing about which.
    """
    unauthorised = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in to continue.",
        headers={"WWW-Authenticate": _SCHEME},
    )

    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme != _SCHEME or not token:
        raise unauthorised

    principal = read_token(token)
    if principal is None:
        raise unauthorised
    return principal


CurrentCook = Annotated[Principal, Depends(current_principal)]


def require_admin(cook: "CurrentCook") -> Principal:
    """Who is asking, if they administer this instance.

    A 403 rather than a 404: the caller is known and the resource is not a secret, only
    the answer is. Pretending an operator's settings page does not exist would send an
    ordinary cook looking for a bug.
    """
    if not cook.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator of this instance may see that.",
        )
    return cook


CurrentAdmin = Annotated[Principal, Depends(require_admin)]
