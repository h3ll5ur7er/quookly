"""The cook account, as it travels between layers.

A Cook is an account. An Eater is a person cooked for and holds the dietary constraints;
they are separate concepts (ADR-005) and arrive separately.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Cook(BaseModel):
    """A cook account, safe to pass anywhere in the application.

    The password hash is deliberately absent. Anything needing it asks for a
    `StoredCredential`, which keeps credentials on the authentication path instead of
    riding along in every value that happens to describe a cook.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    email: str
    display_name: str
    is_admin: bool
    registered_at: datetime
    # The language they chose, if they have. Absent means "follow the browser".
    locale: str | None = None


class StoredCredential(BaseModel):
    """What authentication needs, and nothing else."""

    model_config = ConfigDict(frozen=True)

    cook_id: int
    password_hash: str
