"""Serving the pictures this instance keeps."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from quookly.managers import media as media_manager
from quookly.routes.dependencies import MaybeCook

router = APIRouter()

#: A stored picture never changes: its name is a UUID minted when it was written, so a new
#: picture is a new name. That makes it safe to cache for a long time, which matters on a
#: phone reading an Academy page in a kitchen.
CACHE_FOR_A_YEAR = "public, max-age=31536000, immutable"


@router.get("/media/{media_id}")
async def read_media(media_id: str, cook: MaybeCook) -> Response:
    """The bytes of a stored picture.

    Signed in, or on a page that has been published. A picture is part of its page rather
    than a separate publication, so it follows the page's rule: approved, and not put away
    (ADR-063).

    Not left to the id being unguessable. That is the absence of an access rule rather
    than one — and today every picture here is an Academy picture, so the first recipe
    photograph would have been published by a decision nobody revisited.
    """
    missing = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such picture.")
    if cook is None and not await media_manager.published(media_id):
        # Absent rather than refused, and the same answer as a picture that is not there:
        # whether this instance holds an unpublished picture with that name is not a
        # stranger's business either.
        raise missing

    found = await media_manager.read(media_id)
    if found is None:
        raise missing
    return Response(
        content=found,
        media_type="image/webp",
        headers={"Cache-Control": CACHE_FOR_A_YEAR},
    )
