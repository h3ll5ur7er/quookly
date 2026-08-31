"""Looking a term up, and reading what it means (ADR-054).

Reinstated after being rejected. Recognition for a contribution really is V11 and really
belongs to `EngagementManager`; the rest did not survive contact, because a Client may not
call Resource Access and "authored and read" had no legal shape without a manager.

Reading is what this does today. Writing, approving and asking a model for an explanation
follow, in that order, so that the part which can be *wrong* arrives last.
"""

from collections.abc import Sequence
from dataclasses import replace

from quookly.access import academy, ingredient, media
from quookly.access import cook as cook_access
from quookly.access.academy import SOURCE_LOCALE
from quookly.contracts.academy import (
    ClaimantView,
    EntryView,
    Listing,
    NewPage,
    PageKind,
    PageSummaryView,
    PageView,
    PictureView,
    Reader,
    Standing,
    Wording,
)
from quookly.contracts.errors import IngredientNotRegistered, PageAlreadyWritten
from quookly.engines import explanation
from quookly.utilities.text import normalise


async def browse(
    reader: Reader,
    kind: PageKind | None = None,
    approved: bool | None = None,
    about: str | None = None,
) -> list[PageSummaryView]:
    """Every page, in the reader's language, in the order they would read them.

    `approved=False` is the review queue. Not an administrator's screen alone: seeing what
    is waiting is how a cook learns their own page has not been read yet.
    """
    locale = await _language(reader)
    if reader.is_a_stranger:
        # Asking for what is unreviewed is asking for what has not been published, and the
        # honest answer to that is *none* rather than the published list — quietly
        # answering a different question is how a caller comes to believe the queue is
        # empty (ADR-063).
        if approved is False:
            return []
        approved = True
    # Asked of the Academy rather than answered by the registry entry, so that each side
    # keeps its own vocabulary — the registry's contracts already sit underneath the
    # Academy's, and answering there would make the two import each other (ADR-061).
    if about is not None:
        found = await ingredient.detail(about)
        if found is None:
            raise IngredientNotRegistered(about)
        return [_summarised(one) for one in await academy.pages_about(found.entry.id, locale)]

    listed = await academy.browse(locale, kind, approved)
    # Once for the whole list. Asking inside the comprehension would ask per page, which
    # on the shipped Academy is fifty round trips to answer one question.
    sitting = await _where_they_sit(listed, locale)
    return [_summarised(one, sitting) for one in listed]


async def _where_they_sit(pages: Sequence[Listing], locale: str) -> dict[int, str]:
    """Where the foods these pages are about sit, by ingredient id.

    Asked of the registry rather than stored on the page: where a carrot sits is a fact
    about the carrot, and a page holding its own copy would be a second answer to drift
    from the first (ADR-061). One query for the whole list rather than one per page.

    It is what lets the Academy be read as *Ingredients > Vegetables > Carrot* instead of
    as one flat alphabet of everything anybody has explained (ADR-067).
    """
    wanted = sorted({one.ingredient_id for one in pages if one.ingredient_id is not None})
    if not wanted:
        return {}
    return {
        entry.id: entry.category_slug
        for entry in (await ingredient.for_ids(wanted, locale)).values()
        if entry.category_slug is not None
    }


def _summarised(one: Listing, sitting: dict[int, str] | None = None) -> PageSummaryView:
    return PageSummaryView(
        # The page's own section, not the one that was asked for. Taking it from the query
        # said "technique" for everything whenever nothing was filtered, which nothing
        # could notice while the Academy had one section.
        slug=one.slug,
        kind=one.kind,
        name=one.name,
        summary=one.summary,
        approved=one.approved,
        category_slug=(
            None if sitting is None or one.ingredient_id is None else sitting.get(one.ingredient_id)
        ),
    )


async def read(slug: str, reader: Reader, is_admin: bool = False) -> PageView | None:
    """One page whole, with the other pages its name belongs to.

    `is_admin` is passed in rather than looked up: the caller is a route holding a signed
    token that already says so, and reading a page should not cost a query to re-learn it.

    A stranger reading a page nobody here has read is told there is no such page —
    *absent rather than refused*, which is what it is: nothing has been published under
    that name (ADR-063).
    """
    found = await academy.detail(slug, await _language(reader))
    if found is None:
        return None
    if reader.is_a_stranger and not found.approved:
        return None
    standing = await academy.standing_of(slug)
    return PageView(
        slug=found.slug,
        kind=found.kind,
        name=found.name,
        summary=found.summary,
        explanation=found.explanation,
        spellings=found.spellings,
        origin=found.origin,
        generated=found.generated,
        approved=found.approved,
        may_rewrite=_may_rewrite(standing, reader.cook_id, is_admin),
        entry=None
        if found.entry is None
        else EntryView(
            slug=found.entry.slug,
            name=found.entry.name,
            kind=found.entry.kind,
            allergens=found.entry.allergens,
            classified=found.entry.classified,
            density=found.entry.density,
            piece_grams=found.entry.piece_grams,
            has_nutrition=found.entry.has_nutrition,
        ),
        caution=found.caution,
        also=[
            ClaimantView(slug=one.slug, name=one.name, summary=one.summary) for one in found.also
        ],
        pictures=[
            PictureView(
                id=one.id,
                media_id=one.media_id,
                description=one.description,
                locale=one.locale,
            )
            for one in found.pictures
        ],
    )


async def claimants(term: str, reader: Reader) -> list[ClaimantView]:
    """Every page that answers to this term.

    The set rather than the answer: a step's word links to the *term*, and one claimant
    opens the page while several offer a chooser (ADR-058).
    """
    # No visibility rule needed here: only an approved page claims a term at all, which is
    # ADR-060 doing the work ADR-063 would otherwise have to repeat.
    return [
        ClaimantView(slug=one.slug, name=one.name, summary=one.summary)
        for one in await academy.claimants_of(term, await _language(reader))
    ]


async def _language(reader: Reader) -> str:
    """The language to read in: the cook's, or the one a stranger asked for."""
    if reader.cook_id is not None:
        return await cook_access.locale_for(reader.cook_id)
    return reader.locale or SOURCE_LOCALE


async def write(
    page: NewPage,
    wording: Wording,
    cook_id: int,
    is_admin: bool = False,
    about: str | None = None,
) -> PageView | None:
    """A page somebody here wrote, in the language they are reading in.

    Which language that is belongs here rather than at the route: the manager is what
    knows a cook has one. A page written in one language is one the other two fall back
    from, which is what makes contributing possible without being a translator.

    Unreviewed, and it stays out of every recipe's words until an administrator has read
    it — readable, listed, and not yet a term anybody's step is matched against (ADR-060).
    """
    locale = await cook_access.locale_for(cook_id)
    # The registry entry an ingredient page is about, named by slug because that is what a
    # screen has and what a person reads. Resolved here rather than taken as an id: an id
    # in a request body is a number a client has to have looked up already.
    named = None
    if about is not None:
        found = await ingredient.detail(about)
        if found is None:
            raise IngredientNotRegistered(about)
        named = found.entry.id
    await academy.write(replace(page, wordings={locale: wording}), cook_id, named)
    return await read(page.slug, Reader(cook_id=cook_id), is_admin)


async def explain(term: str, cook_id: int, is_admin: bool = False) -> PageView | None:
    """Ask a model what a word means, and keep the answer as a page (UC-7.4).

    Refused where this instance already explains the term: that is a conflict rather than
    a second opinion, and generating near-copies nobody asked for is how a review queue
    fills up (ADR-062).

    What comes back is marked as a model's and as read by nobody — so, being unreviewed,
    it claims no terms until a person has read it (ADR-056, ADR-060). The cook who asked
    gets their page; the instance does not get a new word in everybody's recipes.
    """
    locale = await cook_access.locale_for(cook_id)
    if await academy.claimants_of(term, locale):
        raise PageAlreadyWritten(term)

    # Which section it belongs in. The Academy has two, and a word the registry knows the
    # name of is a food rather than something you do (ADR-057). Filing every generated page
    # as a technique left the ingredient section of a shipped instance permanently empty,
    # and a page about a food that names no food cannot show that food's facts (ADR-061).
    #
    # `resolve` and not `search`: it is exact and refuses an ambiguous name, which is the
    # conservative direction here. A near-match filed as a page *about* the wrong entry
    # would show one food's allergens under another food's name, and a technique wrongly
    # left in the technique section is only a page in the wrong list.
    food = await ingredient.resolve(term, locale)

    wording = await explanation.explain(term, locale)
    slug = _slugged(term)
    await academy.write(
        NewPage(
            slug=slug,
            kind=PageKind.TECHNIQUE if food is None else PageKind.INGREDIENT,
            wordings={locale: wording},
        ),
        cook_id=None,
        ingredient_id=None if food is None else food.id,
        generated=True,
    )
    return await read(slug, Reader(cook_id=cook_id), is_admin)


def _slugged(term: str) -> str:
    """A term as a slug: lower case, words joined by hyphens, nothing else kept."""
    folded = normalise(term)
    return "-".join(folded.split()) or "explained"


async def may_rewrite(slug: str, cook_id: int, is_admin: bool) -> bool:
    """Whether this cook may rewrite this page's wording."""
    return _may_rewrite(await academy.standing_of(slug), cook_id, is_admin)


def _may_rewrite(standing: Standing | None, cook_id: int | None, is_admin: bool) -> bool:
    """The rule, in one place.

    An administrator always may, because a correction changes what every cook here reads.
    An author may while nobody has approved their page: a draft is not yet the instance's
    prose, and somebody who cannot fix their own typo will not write a second page
    (ADR-060).
    """
    if is_admin:
        return True
    if standing is None or cook_id is None:
        return False
    return not standing.approved and standing.written_by == cook_id


async def decline(slug: str, cook_id: int) -> bool:
    """Put a page away. Returns whether there was one.

    Archived rather than deleted, the same choice a recipe put away makes: it leaves the
    Academy, the queue, and every recipe's words, and nothing is destroyed.
    """
    return await academy.archive(slug)


async def amend(
    slug: str, locale: str, wording: Wording, cook_id: int, is_admin: bool = False
) -> PageView | None:
    """Rewrite one language's wording, and hand the page back as the editor will read it."""
    await academy.amend(slug, locale, wording)
    return await read(slug, Reader(cook_id=cook_id), is_admin)


async def approve(slug: str, cook_id: int, is_admin: bool = False) -> PageView | None:
    """Record that somebody has read this page."""
    await academy.approve(slug)
    return await read(slug, Reader(cook_id=cook_id), is_admin)


async def illustrate(slug: str, upload: bytes, description: str, cook_id: int) -> PageView | None:
    """Put a picture on a page.

    The file is re-encoded and kept beside the database; the page holds the id it was given
    (see `MediaAccess`). The description is the alt text, written in the language the
    administrator is reading in — which is not always the reader's, and the page says so
    rather than handing somebody English silently.
    """
    locale = await cook_access.locale_for(cook_id)
    media_id = await media.store_image(upload)
    await academy.add_picture(slug, media_id, description, locale)
    return await read(slug, Reader(cook_id=cook_id))


async def unillustrate(slug: str, picture_id: int, cook_id: int) -> PageView | None:
    """Take a picture off a page. The file stays — see `MediaAccess`."""
    if not await academy.remove_picture(slug, picture_id):
        return None
    return await read(slug, Reader(cook_id=cook_id))
