"""Academy endpoints."""

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from quookly.contracts.academy import (
    ClaimantView,
    NewPage,
    PageKind,
    PageSummaryView,
    PageView,
    Wording,
)
from quookly.contracts.errors import (
    IngredientNotNamed,
    IngredientNotRegistered,
    PageAlreadyWritten,
    PageNotWritten,
    UnreadableImage,
)
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


class NewPageInput(WordingInput):
    """A page somebody here is writing, in the one language they are writing it in.

    A wording plus an identity. Written in one language rather than all of them: a cook who
    knows how to spatchcock a chicken is not thereby a translator, and a page that arrives
    in one language is a page the other two fall back from (ADR-057).
    """

    #: Lower case, digits and hyphens, like every other slug here. It is what an author's
    #: `[[link]]` names, so it has to be typeable and stable (ADR-059).
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    kind: PageKind = PageKind.TECHNIQUE
    #: The registry entry this page is about, for the ingredient section. Required there
    #: and meaningless elsewhere: a page about a food shows that food's facts by reading
    #: them, and there is nothing to read without one (ADR-061).
    about: str | None = None


@router.get("/academy", response_model=list[PageSummaryView])
async def browse_academy(
    cook: CurrentCook,
    kind: PageKind | None = Query(default=None, description="Show one section on its own."),
    approved: bool | None = Query(
        default=None, description="Narrow to what has been reviewed, or to what awaits it."
    ),
    about: str | None = Query(
        default=None, description="Only the pages written about one registry entry."
    ),
) -> list[PageSummaryView]:
    """Every page, in the cook's language, ordered by the name they will read.

    Pages nobody has reviewed are listed: approval gates what a page may attach itself to,
    not whether it can be read (ADR-060). Pages put away are not listed at all.
    """
    try:
        return await academy_manager.browse(cook.cook_id, kind, approved, about)
    except IngredientNotRegistered as unknown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No such ingredient in the registry.",
        ) from unknown


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
    found = await academy_manager.read(slug, cook.cook_id, cook.is_admin)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such page.")
    return found


@router.post("/academy", response_model=PageView, status_code=status.HTTP_201_CREATED)
async def write_page(submitted: NewPageInput, cook: CurrentCook) -> PageView:
    """Write a page for the Academy.

    Any signed-in cook may: this instance's door is already the membership decision, so a
    separate contributor role would be a second one (ADR-049, ADR-060).

    It arrives unreviewed, and until an administrator has read it, it is a page in the
    Academy and not a word in anybody's recipe — readable and listed, but not matched into
    a step and not what `/academy/terms/{term}` answers with.
    """
    try:
        written = await academy_manager.write(
            NewPage(
                slug=submitted.slug,
                kind=submitted.kind,
                wordings={},
            ),
            Wording(
                name=submitted.name,
                spellings=submitted.spellings,
                summary=submitted.summary,
                explanation=submitted.explanation,
                caution=submitted.caution,
                name_matches=submitted.name_matches,
            ),
            cook.cook_id,
            cook.is_admin,
            submitted.about,
        )
    except IngredientNotNamed as unnamed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A page about an ingredient has to say which ingredient.",
        ) from unnamed
    except IngredientNotRegistered as unknown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No such ingredient in the registry.",
        ) from unknown
    except PageAlreadyWritten as taken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is already a page with that name.",
        ) from taken
    if written is None:
        raise NOT_FOUND
    return written


@router.delete("/academy/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def decline_page(slug: str, admin: CurrentAdmin) -> None:
    """Put a page away.

    How a page nobody wants is declined, and how one that has gone wrong is taken down.
    Archived rather than deleted, the same choice a recipe makes: it leaves the Academy,
    the review queue and every recipe's words, and nothing is destroyed on somebody's
    behalf.
    """
    if not await academy_manager.decline(slug, admin.cook_id):
        raise NOT_FOUND


@router.put("/academy/{slug}/wordings/{locale}", response_model=PageView)
async def amend_page(slug: str, locale: str, wording: WordingInput, cook: CurrentCook) -> PageView:
    """Rewrite one language's wording of a page.

    An administrator's, because the Academy is shared: a correction changes what every cook
    on this instance reads. A locale the page does not speak yet is added, which is how a
    translation arrives.

    The one exception is an author working on a page nobody has approved. That is not yet
    what the instance reads, and an author who cannot fix their own typo will not write a
    second page (ADR-060). Approval is the moment it stops being theirs.

    It does not approve the page — fixing a sentence is not saying somebody has read it.
    """
    if not await academy_manager.may_rewrite(slug, cook.cook_id, cook.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This page is not yours to rewrite.",
        )
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
            cook.cook_id,
            cook.is_admin,
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
        approved = await academy_manager.approve(slug, admin.cook_id, admin.is_admin)
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
