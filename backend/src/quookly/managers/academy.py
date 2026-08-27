"""Looking a term up, and reading what it means (ADR-054).

Reinstated after being rejected. Recognition for a contribution really is V11 and really
belongs to `EngagementManager`; the rest did not survive contact, because a Client may not
call Resource Access and "authored and read" had no legal shape without a manager.

Reading is what this does today. Writing, approving and asking a model for an explanation
follow, in that order, so that the part which can be *wrong* arrives last.
"""

from dataclasses import replace

from quookly.access import academy, ingredient, media
from quookly.access import cook as cook_access
from quookly.contracts.academy import (
    ClaimantView,
    EntryView,
    Listing,
    NewPage,
    PageKind,
    PageSummaryView,
    PageView,
    PictureView,
    Standing,
    Wording,
)
from quookly.contracts.errors import IngredientNotRegistered


async def browse(
    cook_id: int,
    kind: PageKind | None = None,
    approved: bool | None = None,
    about: str | None = None,
) -> list[PageSummaryView]:
    """Every page, in the reader's language, in the order they would read them.

    `approved=False` is the review queue. Not an administrator's screen alone: seeing what
    is waiting is how a cook learns their own page has not been read yet.
    """
    locale = await cook_access.locale_for(cook_id)
    # Asked of the Academy rather than answered by the registry entry, so that each side
    # keeps its own vocabulary — the registry's contracts already sit underneath the
    # Academy's, and answering there would make the two import each other (ADR-061).
    if about is not None:
        found = await ingredient.detail(about)
        if found is None:
            raise IngredientNotRegistered(about)
        return [_summarised(one) for one in await academy.pages_about(found.entry.id, locale)]

    return [
        PageSummaryView(
            # The page's own section, not the one that was asked for. Taking it from the
            # query said "technique" for everything whenever nothing was filtered, which
            # nothing could notice while the Academy had one section.
            slug=one.slug,
            kind=one.kind,
            name=one.name,
            summary=one.summary,
            approved=one.approved,
        )
        for one in await academy.browse(locale, kind, approved)
    ]


def _summarised(one: Listing) -> PageSummaryView:
    return PageSummaryView(
        slug=one.slug,
        kind=one.kind,
        name=one.name,
        summary=one.summary,
        approved=one.approved,
    )


async def read(slug: str, cook_id: int, is_admin: bool = False) -> PageView | None:
    """One page whole, with the other pages its name belongs to.

    `is_admin` is passed in rather than looked up: the caller is a route holding a signed
    token that already says so, and reading a page should not cost a query to re-learn it.
    """
    found = await academy.detail(slug, await cook_access.locale_for(cook_id))
    if found is None:
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
        may_rewrite=_may_rewrite(standing, cook_id, is_admin),
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


async def claimants(term: str, cook_id: int) -> list[ClaimantView]:
    """Every page that answers to this term.

    The set rather than the answer: a step's word links to the *term*, and one claimant
    opens the page while several offer a chooser (ADR-058).
    """
    locale = await cook_access.locale_for(cook_id)
    return [
        ClaimantView(slug=one.slug, name=one.name, summary=one.summary)
        for one in await academy.claimants_of(term, locale)
    ]


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
    return await read(page.slug, cook_id, is_admin)


async def may_rewrite(slug: str, cook_id: int, is_admin: bool) -> bool:
    """Whether this cook may rewrite this page's wording."""
    return _may_rewrite(await academy.standing_of(slug), cook_id, is_admin)


def _may_rewrite(standing: Standing | None, cook_id: int, is_admin: bool) -> bool:
    """The rule, in one place.

    An administrator always may, because a correction changes what every cook here reads.
    An author may while nobody has approved their page: a draft is not yet the instance's
    prose, and somebody who cannot fix their own typo will not write a second page
    (ADR-060).
    """
    if is_admin:
        return True
    if standing is None:
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
    return await read(slug, cook_id, is_admin)


async def approve(slug: str, cook_id: int, is_admin: bool = False) -> PageView | None:
    """Record that somebody has read this page."""
    await academy.approve(slug)
    return await read(slug, cook_id, is_admin)


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
    return await read(slug, cook_id)


async def unillustrate(slug: str, picture_id: int, cook_id: int) -> PageView | None:
    """Take a picture off a page. The file stays — see `MediaAccess`."""
    if not await academy.remove_picture(slug, picture_id):
        return None
    return await read(slug, cook_id)
