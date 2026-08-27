"""Reading a stored picture.

Thin, and deliberately still a manager: a route may not call resource access, and the first
thing that will want to change here — who may see a picture once pages can be published —
would have nowhere to go but into the route.
"""

from quookly.access import academy, media


async def published(media_id: str) -> bool:
    """Whether this picture may be served to somebody with no account.

    Asked of the Academy rather than decided here: a picture is part of a page, and the
    page already knows whether it has been published (ADR-063).
    """
    return await academy.is_published(media_id)


async def read(media_id: str) -> bytes | None:
    """The bytes of a stored picture, or nothing where there is no such picture."""
    return await media.fetch_image(media_id)
