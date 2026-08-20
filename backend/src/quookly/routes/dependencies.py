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
