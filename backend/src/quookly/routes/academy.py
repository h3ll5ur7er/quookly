"""Academy endpoints."""

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from quookly.contracts.academy import (
    ClaimantView,
    PageKind,
    PageSummaryView,
    PageView,
    Wording,
)
from quookly.contracts.errors import PageNotWritten, UnreadableImage
from quookly.managers import academy as academy_manager
from quookly.routes.dependencies import CurrentAdmin, CurrentCook

router = APIRouter()

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such page.")


class WordingInput(BaseModel):
    """A page as one language should now read.

    The whole wording, not a patch: it is a small whole, and patching its spellings would
    need an instruction for reordering that nobody asked for (the reasoning ADR-059 gives
    for recipes).
    """

    name: str = Field(min_length=1, max_length=200)
    #: What a recipe step is matched against (ADR-055). Editing these edits what the recipe
    #: screens underline, which is why they are here rather than derived from the name.
    spellings: list[str] = []
    summary: str = Field(min_length=1, max_length=400)
    explanation: str = Field(min_length=1)
    #: Only where getting it wrong matters. A warning on everything is a warning on nothing.
    caution: str | None = None
    #: Whether the name on its own reliably means this page. German `sieben` is *to sift*
    #: and *the number seven*, and "sieben Minuten" is not about a sieve.
    name_matches: bool = True


@router.get("/academy", response_model=list[PageSummaryView])
async def browse_academy(
    cook: CurrentCook,
    kind: PageKind | None = Query(default=None, description="Show one section on its own."),
) -> list[PageSummaryView]:
    """Every page, in the cook's language, ordered by the name they will read."""
    return await academy_manager.browse(cook.cook_id, kind)


@router.get("/academy/terms/{term}", response_model=list[ClaimantView])
async def pages_for_term(term: str, cook: CurrentCook) -> list[ClaimantView]:
    """Every page that answers to a term.

    Declared **before** `/academy/{slug}`, or that route would swallow it. A step's word
    links here rather than to a page: one claimant opens it, several offer a chooser, and
    nothing picks arbitrarily (ADR-058).
    """
    return await academy_manager.claimants(term, cook.cook_id)


@router.get("/academy/{slug}", response_model=PageView)
async def read_page(slug: str, cook: CurrentCook) -> PageView:
    """One page, with the other pages its name belongs to named at the top."""
    found = await academy_manager.read(slug, cook.cook_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such page.")
    return found


@router.put("/academy/{slug}/wordings/{locale}", response_model=PageView)
async def amend_page(
    slug: str, locale: str, wording: WordingInput, admin: CurrentAdmin
) -> PageView:
    """Rewrite one language's wording of a page.

    An administrator's, because the Academy is shared: a correction changes what every cook
    on this instance reads. A locale the page does not speak yet is added, which is how a
    translation arrives.

    It does not approve the page — fixing a sentence is not saying somebody has read it.
    """
    try:
        amended = await academy_manager.amend(
            slug,
            locale,
            Wording(
                name=wording.name,
                spellings=wording.spellings,
                summary=wording.summary,
                explanation=wording.explanation,
                caution=wording.caution,
                name_matches=wording.name_matches,
            ),
            admin.cook_id,
        )
    except PageNotWritten as absent:
        raise NOT_FOUND from absent
    if amended is None:
        raise NOT_FOUND
    return amended


@router.post("/academy/{slug}/approved", response_model=PageView)
async def approve_page(slug: str, admin: CurrentAdmin) -> PageView:
    """Record that somebody here has read this page.

    What stops a page a model wrote from reading as unchecked (ADR-056). It says nothing
    about who wrote it: vouching for a paragraph and having written it are different facts.
    """
    try:
        approved = await academy_manager.approve(slug, admin.cook_id)
    except PageNotWritten as absent:
        raise NOT_FOUND from absent
    if approved is None:
        raise NOT_FOUND
    return approved


#: What an upload may weigh before it is refused. Generous for a photograph and small
#: enough that a page cannot be used as somebody's file store.
LARGEST_UPLOAD = 12 * 1024 * 1024


@router.post("/academy/{slug}/pictures", response_model=PageView)
async def illustrate_page(
    slug: str,
    admin: CurrentAdmin,
    picture: UploadFile = File(description="A photograph of the thing this page explains."),
    description: str = Form(
        min_length=1,
        max_length=300,
        description="What the picture shows, for somebody who cannot see it.",
    ),
) -> PageView:
    """Put a picture on a page.

    The description is required, not optional: a picture without alt text is an
    accessibility failure, and the rule here is that accessibility is checked as it is
    built rather than retrofitted.
    """
    upload = await picture.read()
    if len(upload) > LARGEST_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="That picture is larger than this instance accepts.",
        )
    try:
        illustrated = await academy_manager.illustrate(slug, upload, description, admin.cook_id)
    except UnreadableImage as unreadable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That file is not a picture this instance can read.",
        ) from unreadable
    except PageNotWritten as absent:
        raise NOT_FOUND from absent
    if illustrated is None:
        raise NOT_FOUND
    return illustrated


@router.delete("/academy/{slug}/pictures/{picture_id}", response_model=PageView)
async def unillustrate_page(slug: str, picture_id: int, admin: CurrentAdmin) -> PageView:
    """Take a picture off a page.

    The file itself stays. A reference changing is not evidence that nobody wants the
    bytes, and collecting what is no longer referred to is a job for a command somebody
    runs deliberately.
    """
    removed = await academy_manager.unillustrate(slug, picture_id, admin.cook_id)
    if removed is None:
        raise NOT_FOUND
    return removed
