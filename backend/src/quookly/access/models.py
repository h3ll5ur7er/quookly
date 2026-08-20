"""SQLModel table definitions.

These types never leave the access layer — an import-linter contract enforces it
(ADR-008, ADR-018). Resource access services translate them into `quookly.contracts`.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class CookRow(SQLModel, table=True):
    """A cook account as stored."""

    __tablename__ = "cook"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    display_name: str
    password_hash: str
    is_admin: bool = Field(default=False)
    registered_at: datetime = Field(default_factory=_now)
