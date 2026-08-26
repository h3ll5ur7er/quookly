"""Looking a term up, and reading what it means (ADR-054).

Reinstated after being rejected. Recognition for a contribution really is V11 and really
belongs to `EngagementManager`; the rest did not survive contact, because a Client may not
call Resource Access and "authored and read" had no legal shape without a manager.

Reading is what this does today. Writing, approving and asking a model for an explanation
follow, in that order, so that the part which can be *wrong* arrives last.
"""

from quookly.access import academy
from quookly.access import cook as cook_access
from quookly.contracts.academy import ClaimantView, PageKind, PageSummaryView, PageView


async def browse(cook_id: int, kind: PageKind | None = None) -> list[PageSummaryView]:
    """Every page, in the reader's language, in the order they would read them."""
    locale = await cook_access.locale_for(cook_id)
    return [
        PageSummaryView(
            slug=one.slug, kind=kind or PageKind.TECHNIQUE, name=one.name, summary=one.summary
        )
        for one in await academy.browse(locale, kind)
    ]


async def read(slug: str, cook_id: int) -> PageView | None:
    """One page whole, with the other pages its name belongs to."""
    found = await academy.detail(slug, await cook_access.locale_for(cook_id))
    if found is None:
        return None
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
        caution=found.caution,
        also=[
            ClaimantView(slug=one.slug, name=one.name, summary=one.summary) for one in found.also
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
