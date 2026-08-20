"""Account endpoints.

Client services: resolve the request, call one manager, translate domain errors into
status codes. No business logic lives here.
"""

from fastapi import APIRouter, HTTPException, status

from quookly.contracts.accounts import (
    Authenticated,
    BootstrapState,
    Credentials,
    Registration,
)
from quookly.contracts.errors import (
    BootstrapClosed,
    EmailAlreadyRegistered,
    InvalidCredentials,
)
from quookly.managers import account as account_manager

router = APIRouter()


@router.get("/accounts/bootstrap", response_model=BootstrapState)
async def get_bootstrap_state() -> BootstrapState:
    """Whether this instance still needs its first admin. Public by necessity."""
    return BootstrapState(required=await account_manager.bootstrap_required())


@router.post(
    "/accounts/bootstrap", response_model=Authenticated, status_code=status.HTTP_201_CREATED
)
async def bootstrap_admin(registration: Registration) -> Authenticated:
    """Claim a fresh instance by creating its first, admin, account."""
    try:
        return await account_manager.bootstrap_admin(registration)
    except BootstrapClosed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This instance already has an account.",
        ) from None
    except EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already registered.",
        ) from None


@router.post("/accounts", response_model=Authenticated, status_code=status.HTTP_201_CREATED)
async def register_cook(registration: Registration) -> Authenticated:
    """Create an account."""
    try:
        return await account_manager.register(registration)
    except EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already registered.",
        ) from None


@router.post("/accounts/sign-in", response_model=Authenticated)
async def sign_in(credentials: Credentials) -> Authenticated:
    """Exchange credentials for a token."""
    try:
        return await account_manager.sign_in(credentials)
    except InvalidCredentials:
        # One message for both a missing account and a wrong password: anything more
        # specific tells a stranger which emails hold accounts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Those credentials did not match an account.",
        ) from None
