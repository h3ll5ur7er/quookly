"""Access to cook accounts, in domain verbs.

Interfaces speak the domain, not the storage model: `register` and `fetch_by_email`
rather than inserts and rows.
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select

from quookly.access.database import session
from quookly.access.models import CookRow
from quookly.contracts.cook import Cook, StoredCredential
from quookly.contracts.errors import EmailAlreadyRegistered


def normalise_email(email: str) -> str:
    """Fold the variations that mean the same person.

    Someone typing `Cook@Example.COM ` at a login form is the account holder, not a new
    account. Normalising on the way in is what makes the unique index mean what it says.
    """
    return email.strip().lower()


def _to_contract(row: CookRow) -> Cook:
    assert row.id is not None, "a persisted cook always has an id"
    return Cook(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        is_admin=row.is_admin,
        registered_at=row.registered_at,
    )


async def register(
    email: str, display_name: str, password_hash: str, *, is_admin: bool = False
) -> Cook:
    """Create an account. Raises `EmailAlreadyRegistered` if the email is taken."""
    row = CookRow(
        email=normalise_email(email),
        display_name=display_name,
        password_hash=password_hash,
        is_admin=is_admin,
    )
    async with session() as active:
        active.add(row)
        try:
            await active.commit()
        except IntegrityError as exc:
            raise EmailAlreadyRegistered(email) from exc
        await active.refresh(row)
        return _to_contract(row)


async def fetch_by_email(email: str) -> Cook | None:
    async with session() as active:
        row = (
            await active.exec(select(CookRow).where(CookRow.email == normalise_email(email)))
        ).first()
    return _to_contract(row) if row else None


async def fetch_credential(email: str) -> StoredCredential | None:
    """The stored hash, for authentication only."""
    async with session() as active:
        row = (
            await active.exec(select(CookRow).where(CookRow.email == normalise_email(email)))
        ).first()
    if row is None or row.id is None:
        return None
    return StoredCredential(cook_id=row.id, password_hash=row.password_hash)


async def any_registered() -> bool:
    """Whether the instance has any account at all.

    The first-admin bootstrap opens only while this is false (FR-16).
    """
    async with session() as active:
        total = (await active.exec(select(func.count()).select_from(CookRow))).one()
    return bool(total)
