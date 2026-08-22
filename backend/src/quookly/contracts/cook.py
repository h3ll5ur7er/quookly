"""The cook account, as it travels between layers.

A Cook is an account. An Eater is a person cooked for and holds the dietary constraints;
they are separate concepts (ADR-005) and arrive separately.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Standing(Enum):
    """Where an account is in the process of being let in (FR-16, UC-10.6).

    Anybody may apply to a Quookly instance; an administrator decides. Three states rather
    than a boolean, because *not yet looked at* and *looked at and declined* are different
    facts and the applicant is owed a different sentence for each.

    `APPLIED` is the default on purpose. A code path that forgets to set this leaves
    somebody locked out, which is recoverable; the opposite mistake lets a stranger into a
    household's kitchen.
    """

    APPLIED = "applied"
    APPROVED = "approved"
    REFUSED = "refused"


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
    standing: Standing
    registered_at: datetime
    # The language they chose, if they have. Absent means "follow the browser".
    locale: str | None = None


class StoredCredential(BaseModel):
    """What authentication needs, and nothing else."""

    model_config = ConfigDict(frozen=True)

    cook_id: int
    password_hash: str
