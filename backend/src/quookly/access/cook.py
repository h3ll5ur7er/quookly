"""Access to cook accounts, in domain verbs.

Interfaces speak the domain, not the storage model: `register` and `fetch_by_email`
rather than inserts and rows.
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select

from quookly.access.database import session
from quookly.access.models import CookRow
from quookly.contracts.cook import Cook, Standing, StoredCredential
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
        standing=row.standing,
        registered_at=row.registered_at,
        locale=row.locale,
    )


async def register(
    email: str,
    display_name: str,
    password_hash: str,
    *,
    is_admin: bool = False,
    standing: Standing = Standing.APPLIED,
) -> Cook:
    """Create an account. Raises `EmailAlreadyRegistered` if the email is taken.

    `standing` is stated by the caller rather than defaulted to approved, so that letting
    somebody in is always a decision written at the call site.
    """
    row = CookRow(
        email=normalise_email(email),
        display_name=display_name,
        password_hash=password_hash,
        is_admin=is_admin,
        standing=standing,
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


#: The language the registry is defined in, and the one every instance can answer in.
DEFINING_LOCALE = "en-GB"


async def locale_for(cook_id: int) -> str:
    """The language this cook reads in — theirs if they have chosen, else English.

    The fallback lives here for the same reason unit preferences merge their defaults
    here: a caller wants an answer, and making every one of them reason about a cook who
    has not chosen yet is how two of them come to disagree.
    """
    row = await fetch(cook_id)
    return row.locale if row is not None and row.locale else DEFINING_LOCALE


async def fetch(cook_id: int) -> Cook | None:
    async with session() as active:
        row = await active.get(CookRow, cook_id)
    return _to_contract(row) if row else None


async def choose_locale(cook_id: int, locale: str) -> Cook | None:
    """Remember the language this cook reads in, rather than the one their browser asks for.

    Stored on the account so it travels with them: signing in on a borrowed phone should
    not put the interface into that phone's language.
    """
    async with session() as active:
        row = await active.get(CookRow, cook_id)
        if row is None:
            return None
        row.locale = locale
        active.add(row)
        await active.commit()
        await active.refresh(row)
        return _to_contract(row)


async def applicants() -> list[Cook]:
    """Everybody waiting to be let in, oldest first.

    Oldest first because this is a queue somebody works through, and the person who has
    been waiting longest is the one most owed an answer.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(CookRow)
                .where(col(CookRow.standing) == Standing.APPLIED)
                .order_by(col(CookRow.registered_at))
            )
        ).all()
    return [_to_contract(row) for row in rows]


async def decide(cook_id: int, standing: Standing) -> Cook | None:
    """Let an applicant in, or turn them away. Absent if there is no such account."""
    async with session() as active:
        row = await active.get(CookRow, cook_id)
        if row is None:
            return None
        row.standing = standing
        active.add(row)
        await active.commit()
        await active.refresh(row)
        return _to_contract(row)
