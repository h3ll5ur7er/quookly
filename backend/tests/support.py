"""Helpers the route tests share.

`sign_up` lived in seventeen files as seventeen copies of the same four lines. It stopped
being copyable the moment accounts had to be applied for and approved, which is the usual
way a duplicated helper announces itself.
"""

from typing import Any

from httpx import AsyncClient

from quookly.access import cook as cook_access
from quookly.contracts.cook import Standing

APPLICATIONS = "/api/v1/accounts/applications"
SIGN_IN = "/api/v1/accounts/sign-in"

#: Long enough for the `Registration` contract, and the same everywhere so that a test
#: reading a fixture does not have to wonder whether the password is the point.
PASSWORD = "a-sufficiently-long-password"


async def sign_up(
    client: AsyncClient, email: str, *, display_name: str = "Emanuel", password: str = PASSWORD
) -> dict[str, str]:
    """An approved account with a token, in one call.

    Approved through `CookAccess` rather than through the admin endpoint: these tests are
    about eaters and pantries and plans, and making each of them bootstrap an admin first
    to open a door would be setting up by exercising a feature they are not testing.
    Whether that door works is `test_accounts.py`'s question.
    """
    applied: dict[str, Any] = (
        await client.post(
            APPLICATIONS,
            json={"email": email, "display_name": display_name, "password": password},
        )
    ).json()
    await cook_access.decide(applied["id"], Standing.APPROVED)

    token = (await client.post(SIGN_IN, json={"email": email, "password": password})).json()
    return {"Authorization": f"Bearer {token['token']}"}
