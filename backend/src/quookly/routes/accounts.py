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
from quookly.contracts.cook import Cook
from quookly.contracts.errors import (
    BootstrapClosed,
    EmailAlreadyRegistered,
    InvalidCredentials,
    NotYetApproved,
    Refused,
)
from quookly.managers import account as account_manager
from quookly.managers import seed as seed_manager
from quookly.routes.dependencies import CurrentAdmin, CurrentCook

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
        authenticated = await account_manager.bootstrap_admin(registration)
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

    # The first cook should land on a kitchen with something in it (UC-10.4).
    await seed_manager.install_starter_recipes(authenticated.cook.id)
    return authenticated


@router.post("/accounts/applications", response_model=Cook, status_code=status.HTTP_201_CREATED)
async def apply_for_account(registration: Registration) -> Cook:
    """Ask to be let in (UC-10.6).

    Public, and no token comes back. An application is not an account yet, and an endpoint
    that handed one over would be open registration wearing a different name.
    """
    try:
        return await account_manager.apply(registration)
    except EmailAlreadyRegistered:
        # Deliberately the same answer whether the address holds an account or an earlier
        # application: which of the two it is, is not a stranger's business.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already registered.",
        ) from None


@router.get("/accounts/applications", response_model=list[Cook])
async def list_applications(admin: CurrentAdmin) -> list[Cook]:
    """Who is waiting to be let in, oldest first (UC-10.6)."""
    return await account_manager.applicants()


@router.post("/accounts/applications/{cook_id}/approved", response_model=Cook)
async def approve_application(cook_id: int, admin: CurrentAdmin) -> Cook:
    """Let somebody in (UC-10.6).

    They land on a kitchen with something in it, for the same reason the first admin does
    (UC-10.4): an empty app teaches nobody what it is for.
    """
    decided = await account_manager.decide(cook_id, approved=True)
    if decided is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such account.")
    await seed_manager.install_starter_recipes(decided.id)
    return decided


@router.post("/accounts/applications/{cook_id}/refused", response_model=Cook)
async def refuse_application(cook_id: int, admin: CurrentAdmin) -> Cook:
    """Turn somebody away (UC-10.6). Reversible: an admin can approve them later."""
    decided = await account_manager.decide(cook_id, approved=False)
    if decided is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such account.")
    return decided


@router.get("/accounts/me", response_model=Cook)
async def get_current_cook(cook: CurrentCook) -> Cook:
    """The signed-in account, for a client that has a token and wants the rest.

    A token carries an id and an admin flag and deliberately nothing else, so a page that
    needs the cook's name or chosen language asks for it rather than reading it out of a
    credential.
    """
    account = await account_manager.fetch(cook.cook_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such account.")
    return account


@router.post("/accounts/sign-in", response_model=Authenticated)
async def sign_in(credentials: Credentials) -> Authenticated:
    """Exchange credentials for a token."""
    try:
        return await account_manager.sign_in(credentials)
    except NotYetApproved:
        # 403 rather than 401: the credentials were right. Retrying them changes nothing,
        # and a client that treats this as "sign in again" would loop.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your application is waiting for an administrator of this instance.",
        ) from None
    except Refused:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An administrator of this instance declined this account.",
        ) from None
    except InvalidCredentials:
        # One message for both a missing account and a wrong password: anything more
        # specific tells a stranger which emails hold accounts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Those credentials did not match an account.",
        ) from None
