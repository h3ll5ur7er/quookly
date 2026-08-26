"""Access to the Academy's pages, in domain verbs.

Shaped like `IngredientAccess` on purpose: a page has a slug, a canonical name and its
spellings per locale, a provenance and a review state, and the same things go wrong with
it (ADR-057).

Where it parts company is ambiguity. The registry refuses a name a second entry claims;
here several pages may claim a term and the page names the others at the top, because
nothing computes on a page and a person resolves it by clicking (ADR-058).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.models import (
    AcademyPageRow,
    AcademyPictureRow,
    AcademyTermRow,
    AcademyTextRow,
)
from quookly.contracts.academy import (
    Claimant,
    Listing,
    NewPage,
    Page,
    PageKind,
    Picture,
    Standing,
    Wording,
)
from quookly.contracts.errors import PageAlreadyWritten, PageNotWritten
from quookly.contracts.ingredient import Origin
from quookly.contracts.matching import Named
from quookly.utilities.text import fold, normalise

#: The language pages are seeded in, and the fallback for one written in no other. The
#: same reach `IngredientAccess` gives a name: a page a cook cannot read might as well not
#: be there.
SOURCE_LOCALE = "en-GB"


async def store_many(pages: Sequence[NewPage], origin: Origin = Origin.USER) -> int:
    """Add the pages this instance does not have. Returns how many were new.

    Skips a slug already here rather than raising, because start-up runs this every boot
    and must not accumulate copies — and must never overwrite what a cook has written
    (ADR-016).

    A seeded page arrives **approved**: nobody signs off what the instance chose to ship.
    Anything else arrives unreviewed, and a generated one says so separately (ADR-056).
    """
    if not pages:
        return 0

    async with session() as active:
        held = {
            row.slug
            for row in (
                await active.exec(
                    select(AcademyPageRow).where(
                        col(AcademyPageRow.slug).in_([page.slug for page in pages])
                    )
                )
            ).all()
        }

        added = 0
        for page in pages:
            if page.slug in held:
                continue
            held.add(page.slug)
            row = AcademyPageRow(
                slug=page.slug,
                kind=page.kind,
                origin=origin,
                approved=origin is Origin.SEED,
            )
            active.add(row)
            await active.flush()
            assert row.id is not None
            _write_wordings(active, row.id, page.wordings)
            added += 1

        await active.commit()
    return added


async def write(page: NewPage, cook_id: int) -> None:
    """One page, written here by somebody on this instance.

    Unreviewed, and recorded against its author. Refuses a slug that is taken rather than
    skipping it the way the bulk path does: a cook told nothing would think it saved.
    """
    async with session() as active:
        taken = (
            await active.exec(select(AcademyPageRow).where(col(AcademyPageRow.slug) == page.slug))
        ).first()
        if taken is not None:
            raise PageAlreadyWritten(f"{page.slug} is already a page")

        row = AcademyPageRow(
            slug=page.slug, kind=page.kind, origin=Origin.USER, approved=False, written_by=cook_id
        )
        active.add(row)
        await active.flush()
        assert row.id is not None
        _write_wordings(active, row.id, page.wordings)
        await active.commit()


async def standing_of(slug: str) -> Standing | None:
    """Where a page stands: read, written by whom, and whether it has been put away.

    Answers for a page that is archived, unlike `detail`. What a caller needs in order to
    decide who may rewrite or restore it, which is a different question from what the page
    says (ADR-060).
    """
    async with session() as active:
        row = (
            await active.exec(select(AcademyPageRow).where(col(AcademyPageRow.slug) == slug))
        ).first()
        if row is None:
            return None
        return Standing(
            approved=row.approved,
            written_by=row.written_by,
            archived=row.archived_at is not None,
        )


async def archive(slug: str) -> bool:
    """Put a page away. Returns whether there was one.

    How an administrator declines a page, and how one that has gone bad is taken down.
    Nothing is destroyed: the row stays, out of the Academy, out of the queue and out of
    every recipe's words.
    """
    async with session() as active:
        row = (
            await active.exec(select(AcademyPageRow).where(col(AcademyPageRow.slug) == slug))
        ).first()
        if row is None:
            return False
        row.archived_at = datetime.now(UTC)
        active.add(row)
        await active.commit()
        return True


async def restore(slug: str) -> bool:
    """Bring a page back. Returns whether there was one.

    Approval is untouched: bringing a page back is not the same act as saying somebody has
    read it, and a page declined after approval comes back approved (ADR-051).
    """
    async with session() as active:
        row = (
            await active.exec(select(AcademyPageRow).where(col(AcademyPageRow.slug) == slug))
        ).first()
        if row is None:
            return False
        row.archived_at = None
        active.add(row)
        await active.commit()
        return True


def _write_wordings(active: AsyncSession, page_id: int, wordings: dict[str, Wording]) -> None:
    """The text and the terms of a page, in every language it is written in."""
    for locale, wording in wordings.items():
        active.add(
            AcademyTextRow(
                page_id=page_id,
                locale=locale,
                name=wording.name,
                summary=wording.summary,
                explanation=wording.explanation,
                caution=wording.caution,
            )
        )
        seen: set[str] = set()
        for position, spelling in enumerate([wording.name, *wording.spellings]):
            wanted = normalise(spelling)
            if not wanted or wanted in seen:
                continue
            seen.add(wanted)
            active.add(
                AcademyTermRow(
                    page_id=page_id,
                    locale=locale,
                    spelling=spelling,
                    normalised=wanted,
                    # The first is what this language calls the thing; the rest are
                    # spellings a step might use.
                    is_canonical=position == 0,
                    # A name that is also an ordinary word stays the name and stops being
                    # something a step is matched against (ADR-055).
                    matchable=position > 0 or wording.name_matches,
                )
            )


async def _texts_for(
    active: AsyncSession, page_ids: list[int], locale: str
) -> dict[int, AcademyTextRow]:
    """One text per page, in the reader's language or the one it was seeded in."""
    if not page_ids:
        return {}
    rows = (
        await active.exec(
            select(AcademyTextRow).where(
                col(AcademyTextRow.page_id).in_(page_ids),
                col(AcademyTextRow.locale).in_([locale, SOURCE_LOCALE]),
            )
        )
    ).all()
    chosen: dict[int, AcademyTextRow] = {}
    for candidate in (locale, SOURCE_LOCALE):
        for row in rows:
            if row.locale == candidate and row.page_id not in chosen:
                chosen[row.page_id] = row
    return chosen


async def browse(
    locale: str, kind: PageKind | None = None, approved: bool | None = None
) -> list[Listing]:
    """Every page, named for the reader, in the order they would read them.

    Alphabetical by the name shown rather than by slug: a German cook looking for
    *unterheben* should not have to know it is filed under `fold`.

    Unreviewed pages are **listed**. Approval gates what a page may attach itself to, not
    whether it can be read (ADR-060) — and an author who cannot see their own page has no
    way to tell it saved. `approved=False` narrows to the review queue.

    Pages put away are not listed at all, whatever is asked for.
    """
    async with session() as active:
        statement = select(AcademyPageRow).where(col(AcademyPageRow.archived_at).is_(None))
        if kind is not None:
            statement = statement.where(col(AcademyPageRow.kind) == kind)
        if approved is not None:
            statement = statement.where(col(AcademyPageRow.approved).is_(approved))
        rows = (await active.exec(statement)).all()
        pages = {row.id: row for row in rows if row.id is not None}
        texts = await _texts_for(active, list(pages), locale)

    listed = [
        Listing(slug=row.slug, name=text.name, summary=text.summary, approved=row.approved)
        for page_id, row in pages.items()
        if (text := texts.get(page_id)) is not None
    ]
    return sorted(listed, key=lambda one: (fold(one.name), one.slug))


async def claimants_of(term: str, locale: str) -> list[Claimant]:
    """Every page that answers to this term, best-known first.

    The set rather than the answer. Several pages may claim a term, and which one somebody
    meant is a question for them rather than for this (ADR-058).
    """
    wanted = fold(term)
    if not wanted:
        return []

    async with session() as active:
        terms = (
            await active.exec(
                select(AcademyTermRow).where(
                    col(AcademyTermRow.locale).in_([locale, SOURCE_LOCALE])
                )
            )
        ).all()
        page_ids = sorted({row.page_id for row in terms if fold(row.normalised) == wanted})
        if not page_ids:
            return []

        # Approved only, and nothing put away. This is where a step's word leads, so a
        # page nobody has read cannot be what a word leads to (ADR-060).
        rows = (
            await active.exec(
                select(AcademyPageRow).where(
                    col(AcademyPageRow.id).in_(page_ids),
                    col(AcademyPageRow.approved).is_(True),
                    col(AcademyPageRow.archived_at).is_(None),
                )
            )
        ).all()
        texts = await _texts_for(active, page_ids, locale)

    found = [
        Claimant(slug=row.slug, name=text.name, summary=text.summary)
        for row in rows
        if row.id is not None and (text := texts.get(row.id)) is not None
    ]
    return sorted(found, key=lambda one: (fold(one.name), one.slug))


async def detail(slug: str, locale: str) -> Page | None:
    """One page whole, with the other pages its name belongs to.

    The hatnote is a query rather than a stored list: the set of claimants changes when
    anybody writes a page, and a stored one would go stale silently.
    """
    async with session() as active:
        row = (
            await active.exec(
                select(AcademyPageRow).where(
                    col(AcademyPageRow.slug) == slug,
                    col(AcademyPageRow.archived_at).is_(None),
                )
            )
        ).first()
        if row is None or row.id is None:
            return None

        texts = await _texts_for(active, [row.id], locale)
        text = texts.get(row.id)
        if text is None:
            return None

        shown = (
            await active.exec(
                select(AcademyPictureRow)
                .where(col(AcademyPictureRow.page_id) == row.id)
                .order_by(col(AcademyPictureRow.position), col(AcademyPictureRow.id))
            )
        ).all()

        spellings = (
            await active.exec(
                select(AcademyTermRow).where(
                    col(AcademyTermRow.page_id) == row.id,
                    col(AcademyTermRow.locale) == text.locale,
                    col(AcademyTermRow.is_canonical).is_(False),
                )
            )
        ).all()

    return Page(
        slug=row.slug,
        kind=row.kind,
        name=text.name,
        summary=text.summary,
        explanation=text.explanation,
        caution=text.caution,
        spellings=[one.spelling for one in spellings],
        origin=row.origin,
        generated=row.generated,
        approved=row.approved,
        also=[one for one in await claimants_of(text.name, locale) if one.slug != slug],
        pictures=[
            Picture(
                id=one.id,
                media_id=one.media_id,
                description=one.description,
                locale=one.locale,
            )
            for one in shown
            if one.id is not None
        ],
    )


async def vocabulary(locale: str) -> tuple[list[Named], dict[str, str]]:
    """Every page and the terms it may be found by, with what each page is called.

    Reference data for a rule engine, so it comes out as plain values: the engine reads no
    database and the vocabulary arrives as an argument.

    Both answers from one query. They were two, and every recipe read paid for both — a
    screen that had no database cost before this feature should not gain two round trips
    to underline a word.

    Terms marked unmatchable are left out. They are still the page's name and still what a
    reader sees — they simply have another life as ordinary words, and "sieben Minuten" is
    not about a sieve.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(AcademyPageRow, AcademyTermRow)
                .join(AcademyTermRow, onclause=col(AcademyTermRow.page_id) == AcademyPageRow.id)
                .where(
                    col(AcademyTermRow.locale).in_([locale, SOURCE_LOCALE]),
                    col(AcademyTermRow.matchable).is_(True),
                    # The whole of ADR-060, in two lines. A page nobody has read is a page
                    # in the Academy and not a word in anybody's recipe, and one put away
                    # is out of every recipe that already used the word.
                    col(AcademyPageRow.approved).is_(True),
                    col(AcademyPageRow.archived_at).is_(None),
                )
            )
        ).all()

        gathered: dict[str, list[str]] = {}
        pages: dict[int, str] = {}
        for page, term in rows:
            gathered.setdefault(page.slug, []).append(term.spelling)
            if page.id is not None:
                pages[page.id] = page.slug

        texts = await _texts_for(active, list(pages), locale)

    named = {slug: texts[page_id].name for page_id, slug in pages.items() if page_id in texts}
    return [Named(slug=slug, names=tuple(terms)) for slug, terms in sorted(gathered.items())], named


async def amend(slug: str, locale: str, wording: Wording) -> None:
    """Rewrite one language's wording of a page.

    Replacement rather than patching, the reason ADR-059 gives for recipes: a wording is a
    small whole, and patching its spellings would need an instruction for reordering that
    nobody asked for.

    A locale the page does not speak yet is added, which is how a translation arrives. The
    other languages are untouched — a page corrected in English has not changed what it
    says in German.

    It does **not** approve the page and does not clear `generated`. Fixing a sentence is
    not saying somebody has read the page (ADR-051), and `generated` records who wrote it
    first — approving is what stops it reading as unchecked (ADR-056).
    """
    async with session() as active:
        page = (
            await active.exec(select(AcademyPageRow).where(col(AcademyPageRow.slug) == slug))
        ).first()
        if page is None or page.id is None:
            raise PageNotWritten(slug)

        for held in (
            await active.exec(
                select(AcademyTextRow).where(
                    col(AcademyTextRow.page_id) == page.id,
                    col(AcademyTextRow.locale) == locale,
                )
            )
        ).all():
            await active.delete(held)
        for term in (
            await active.exec(
                select(AcademyTermRow).where(
                    col(AcademyTermRow.page_id) == page.id,
                    col(AcademyTermRow.locale) == locale,
                )
            )
        ).all():
            await active.delete(term)
        await active.flush()

        _write_wordings(active, page.id, {locale: wording})
        await active.commit()


async def approve(slug: str) -> None:
    """Record that somebody has read this page.

    Only that. It does not change what the page says and does not claim a person wrote it:
    an administrator approving a paragraph a model composed has vouched for it, which is a
    different fact from having written it (ADR-051, ADR-056).

    Idempotent — the useful question is whether anybody has looked.
    """
    async with session() as active:
        page = (
            await active.exec(select(AcademyPageRow).where(col(AcademyPageRow.slug) == slug))
        ).first()
        if page is None:
            raise PageNotWritten(slug)
        page.approved = True
        active.add(page)
        await active.commit()


async def add_picture(slug: str, media_id: str, description: str, locale: str) -> None:
    """Put a picture on a page, after the last one already there."""
    async with session() as active:
        page = (
            await active.exec(select(AcademyPageRow).where(col(AcademyPageRow.slug) == slug))
        ).first()
        if page is None or page.id is None:
            raise PageNotWritten(slug)

        held = (
            await active.exec(
                select(AcademyPictureRow).where(col(AcademyPictureRow.page_id) == page.id)
            )
        ).all()
        active.add(
            AcademyPictureRow(
                page_id=page.id,
                media_id=media_id,
                description=description,
                locale=locale,
                position=len(held),
            )
        )
        await active.commit()


async def remove_picture(slug: str, picture_id: int) -> bool:
    """Take a picture off a page. Returns whether it was there to take off.

    **The file stays.** A reference changing is not evidence that nobody wants the bytes,
    and a sweep that guessed would eventually guess wrong. Collecting what is no longer
    referred to is a job for a CLI command.
    """
    async with session() as active:
        page = (
            await active.exec(select(AcademyPageRow).where(col(AcademyPageRow.slug) == slug))
        ).first()
        if page is None or page.id is None:
            return False
        held = (
            await active.exec(
                select(AcademyPictureRow).where(
                    col(AcademyPictureRow.id) == picture_id,
                    col(AcademyPictureRow.page_id) == page.id,
                )
            )
        ).first()
        if held is None:
            return False
        await active.delete(held)
        await active.commit()
    return True
