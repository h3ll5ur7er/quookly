"""Shapes exchanged when getting into an instance."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from quookly.contracts.cook import Cook

MINIMUM_PASSWORD_LENGTH = 12


class Registration(BaseModel):
    """A request to create an account.

    The password rule lives here rather than in the manager: it constrains the shape of
    the input, so it is the contract's business, and stating it here means the API
    rejects a short password before any work is done.
    """

    model_config = ConfigDict(frozen=True)

    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=MINIMUM_PASSWORD_LENGTH, max_length=1024)


class Credentials(BaseModel):
    """A request to sign in. No length rule — an old password is still the password."""

    model_config = ConfigDict(frozen=True)

    email: str
    password: str


class Authenticated(BaseModel):
    """A signed-in cook and the token proving it."""

    model_config = ConfigDict(frozen=True)

    token: str
    cook: Cook


class BootstrapState(BaseModel):
    """Whether the instance still needs its first admin."""

    model_config = ConfigDict(frozen=True)

    required: bool
