"""Academy endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from quookly.contracts.academy import ClaimantView, PageKind, PageSummaryView, PageView
from quookly.managers import academy as academy_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()


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
