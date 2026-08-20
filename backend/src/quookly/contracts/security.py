"""Who is making a request."""

from pydantic import BaseModel, ConfigDict


class Principal(BaseModel):
    """The authenticated identity behind a request.

    Carries only what authorisation decisions need. Anything more about the cook is
    fetched from the access layer, so a long-lived token cannot go stale about it.
    """

    model_config = ConfigDict(frozen=True)

    cook_id: int
    is_admin: bool
