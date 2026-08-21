"""Access to pages on the web (UC-1.3).

This service knows the shape of the web, not the shape of a recipe. It fetches a URL,
strips the furniture, and returns the readable prose alongside whatever structured
metadata the page embedded — without preferring either. Which to believe is
interpretation, and belongs to V2.

Two things need guarding, and both come from the same fact: the URL is typed by a user and
the fetch happens on the server's network.

**Where it will go.** Only http and https, and only to addresses that are not the
instance's own network. An instance that fetches whatever it is told is a way to read a
router's admin page, a cloud metadata endpoint, or Quookly's own API from inside — things
the person pasting the link cannot reach themselves. Every redirect hop is checked, because
checking only the pasted URL checks nothing.

**How much it will read.** A response is capped. A URL is user input, and a server that
downloads whatever length it is told has handed out a way to exhaust its own memory.
"""

import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura
from lxml import etree
from lxml import html as lxml_html

from quookly.contracts.errors import (
    AddressNotAllowed,
    ContentRefused,
    ContentUnreachable,
    ContentUnreadable,
)
from quookly.contracts.web import ReadableContent
from quookly.utilities.configuration import get_settings
from quookly.utilities.diagnostics import get_logger

log = get_logger("web")

# Generous for a recipe page and far short of a memory problem. The largest recipe blogs
# run to a few hundred kilobytes of markup.
MAXIMUM_BYTES = 4 * 1024 * 1024
MAXIMUM_REDIRECTS = 5

# Sites that decline to serve an automated reader, as opposed to sites that are broken.
# Several large recipe publishers answer 403 to anything without a browser fingerprint.
_REFUSAL_STATUSES = frozenset({401, 403, 429})

# What a page is. Anything else — a PDF, a video, an archive — is not something this can
# read, and downloading one to discover that wastes somebody's bandwidth.
READABLE_TYPES = ("text/html", "application/xhtml+xml", "text/plain")

# A cook pasting a link expects to see what they see in their own browser. Some sites
# serve a stub to anything that does not look like one.
USER_AGENT = "Mozilla/5.0 (compatible; Quookly/1.0; +https://github.com/quookly)"


def _transport() -> httpx.AsyncBaseTransport | None:
    """The transport to use. Replaced in tests; `None` means the real network."""
    return None


def _resolve(host: str) -> list[str]:
    """Every address this host resolves to. Replaced in tests."""
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


def _refuse_private_addresses(url: str) -> None:
    """Refuse anything that is not a public web address.

    Resolving here and checking every answer means a host with one public and one private
    record is refused rather than gambled on.

    A residual gap worth naming: the name is resolved again when the request is made, so a
    server that answers differently the second time can still be reached. Closing that
    means pinning the address through the connection, which httpx does not offer without
    a custom transport. The realistic attack this stops — a pasted link to `localhost` or
    to `169.254.169.254` — does not need that sophistication.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise AddressNotAllowed(f"only http and https addresses are fetched, not {url!r}")

    if get_settings().allow_private_fetch:
        return

    try:
        addresses = _resolve(parsed.hostname)
    except OSError as unresolvable:
        raise ContentUnreachable(f"could not resolve {parsed.hostname}") from unresolvable

    for address in addresses:
        try:
            resolved = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not resolved.is_global:
            raise AddressNotAllowed(
                f"{parsed.hostname} resolves to {resolved}, which is not a public address. "
                "Set QUOOKLY_ALLOW_PRIVATE_FETCH=true to fetch from your own network."
            )


async def _fetch(url: str) -> httpx.Response:
    """Follow the URL by hand, checking every hop.

    Redirects are followed manually rather than by the client, because the check that
    matters is on the address each hop actually goes to.
    """
    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout_seconds,
        transport=_transport(),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        for _ in range(MAXIMUM_REDIRECTS):
            _refuse_private_addresses(url)
            try:
                response = await client.get(url)
            except httpx.HTTPError as unreachable:
                log.warning("page unreachable", extra={"url": url})
                raise ContentUnreachable(f"could not fetch {url}") from unreachable

            if not response.is_redirect:
                if response.status_code in _REFUSAL_STATUSES:
                    # Bot protection, not a broken site. The page works in the cook's own
                    # browser, which is worth saying rather than reporting a failure.
                    raise ContentRefused(
                        f"{url} refused an automated reader ({response.status_code})"
                    )
                if response.status_code >= 400:
                    raise ContentUnreachable(f"{url} answered {response.status_code}")
                return response

            location = response.headers.get("location")
            if not location:
                raise ContentUnreachable(f"{url} redirected without saying where")
            url = str(httpx.URL(url).join(location))

        raise ContentUnreachable(f"too many redirects starting from {url}")


def _structured_data(markup: str) -> list[dict[str, Any]]:
    """Every `application/ld+json` block on the page, as found.

    A block holding an array is unwrapped, because a container is not a meaning. Nothing
    else is interpreted here: which block is a recipe, and whether to believe it, is V2's
    question.

    A block that does not parse is skipped rather than fatal. Real sites ship invalid
    JSON-LD, and losing the page over one helps nobody.
    """
    try:
        tree = lxml_html.fromstring(markup)
    except (ValueError, etree.ParserError):
        return []

    blocks = tree.xpath('//script[@type="application/ld+json"]')
    if not isinstance(blocks, list):
        return []

    found: list[dict[str, Any]] = []
    for element in blocks:
        # `HtmlElement` rather than `_Element`: only the HTML flavour carries the text of
        # a script node, and an xpath result may hold strings and numbers too.
        if not isinstance(element, lxml_html.HtmlElement):
            continue
        raw = (element.text_content() or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            log.info("skipped an unparseable ld+json block")
            continue
        for block in parsed if isinstance(parsed, list) else [parsed]:
            if isinstance(block, dict):
                found.append(block)
    return found


async def fetch_readable(url: str) -> ReadableContent:
    """Fetch a page and reduce it to what is worth reading (UC-1.3)."""
    response = await _fetch(url)

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and not content_type.startswith(READABLE_TYPES):
        raise ContentUnreadable(f"{url} is {content_type}, which is not a page")

    if len(response.content) > MAXIMUM_BYTES:
        raise ContentUnreadable(
            f"{url} is larger than this instance will read ({MAXIMUM_BYTES} bytes)"
        )

    markup = response.text
    # `favor_recall` keeps ingredient lists, which stricter settings drop as boilerplate:
    # a short list of short lines is exactly what a de-boilerplater is built to discard,
    # and here it is the part worth having.
    text = trafilatura.extract(
        markup, favor_recall=True, include_comments=False, include_tables=True
    )
    structured = _structured_data(markup)

    if not (text and text.strip()) and not structured:
        # Handing an empty page to a model produces an invented recipe, which is the one
        # outcome worse than an error.
        raise ContentUnreadable(f"there is nothing readable at {url}")

    metadata = trafilatura.extract_metadata(markup)
    return ReadableContent(
        url=str(response.url),
        text=(text or "").strip(),
        title=getattr(metadata, "title", None) if metadata else None,
        structured=structured,
    )
