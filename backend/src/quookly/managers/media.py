"""Reading a stored picture.

Thin, and deliberately still a manager: a route may not call resource access, and the first
thing that will want to change here — who may see a picture once pages can be published —
would have nowhere to go but into the route.
"""

from quookly.access import media


async def read(media_id: str) -> bytes | None:
    """The bytes of a stored picture, or nothing where there is no such picture."""
    return await media.fetch_image(media_id)
