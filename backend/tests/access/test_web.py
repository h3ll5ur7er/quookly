"""Fetching a page and reducing it to what is worth reading (UC-1.3).

This service knows about the shape of the web, not about recipes. It returns the readable
text *and* whatever structured metadata the page embedded, without judging either — which
of the two to believe is interpretation, and belongs to V2.

The two things worth guarding here are that a page can be very large and that the URL
comes from a user. An instance that fetches whatever it is told is a request-forgery
engine pointed at its own network.
"""

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from pytest import MonkeyPatch

from quookly.access import web
from quookly.contracts.errors import (
    AddressNotAllowed,
    ContentRefused,
    ContentUnreachable,
    ContentUnreadable,
)
from quookly.utilities.configuration import get_settings

PAGE = """
<html>
  <head>
    <title>The Best Pancakes You Will Ever Make</title>
  </head>
  <body>
    <nav><a href="/">Home</a><a href="/about">About my journey</a></nav>
    <article>
      <h1>The Best Pancakes You Will Ever Make</h1>
      <p>My grandmother, on a windswept morning in 1962, first showed me the secret to
      pancakes. It was a Tuesday. The kitchen smelled of rain and possibility, and I have
      never forgotten the way the light fell across the linoleum that day.</p>
      <p>Ingredients: 225g plain flour, 300ml milk, 2 eggs. Whisk the dry ingredients,
      beat in the milk and eggs, rest the batter, and fry until the edges set.</p>
    </article>
    <footer>Subscribe to my newsletter for more stories like this one.</footer>
  </body>
</html>
"""

RECIPE_JSONLD = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Pancakes",
    "recipeYield": "12",
    "recipeIngredient": ["225g plain flour", "300ml milk", "2 eggs"],
}


def page_with(*blocks: Any, body: str = PAGE) -> str:
    """The page, with these blocks embedded. A string block is embedded verbatim, which
    is how a broken one is written."""
    scripts = "".join(
        f'<script type="application/ld+json">'
        f"{block if isinstance(block, str) else json.dumps(block)}"
        f"</script>"
        for block in blocks
    )
    return body.replace("</head>", f"{scripts}</head>")


@pytest.fixture(autouse=True)
def forget_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def public_addresses(monkeypatch: MonkeyPatch) -> None:
    """Every host resolves somewhere public unless a test says otherwise."""
    monkeypatch.setattr(web, "_resolve", lambda host: ["93.184.216.34"])


def stub(handler: Callable[[httpx.Request], httpx.Response], monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(web, "_transport", lambda: httpx.MockTransport(handler))


def serving(
    html: str, status: int = 200, content_type: str = "text/html; charset=utf-8"
) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _: httpx.Response(status, text=html, headers={"content-type": content_type})


class TestReadingAPage:
    async def test_the_recipe_survives(self, monkeypatch: MonkeyPatch) -> None:
        stub(serving(PAGE), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert "225g plain flour" in content.text

    async def test_the_preamble_does_not(self, monkeypatch: MonkeyPatch) -> None:
        """The founding use case is a thousand words of blog around forty of recipe."""
        stub(serving(PAGE), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert "Subscribe to my newsletter" not in content.text
        assert "About my journey" not in content.text

    async def test_the_title_comes_back(self, monkeypatch: MonkeyPatch) -> None:
        stub(serving(PAGE), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert content.title is not None
        assert "Pancakes" in content.title

    async def test_the_url_comes_back(self, monkeypatch: MonkeyPatch) -> None:
        """Provenance: a stored recipe records where it came from (V1)."""
        stub(serving(PAGE), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert content.url == "https://example.com/pancakes"

    async def test_a_page_with_nothing_to_read_is_reported(self, monkeypatch: MonkeyPatch) -> None:
        """Better to say "there is nothing here" than to hand an empty page to a model."""
        stub(serving("<html><body></body></html>"), monkeypatch)
        with pytest.raises(ContentUnreadable):
            await web.fetch_readable("https://example.com/empty")


class TestEmbeddedStructuredData:
    async def test_a_recipe_block_is_returned_as_found(self, monkeypatch: MonkeyPatch) -> None:
        """Most recipe sites publish schema.org data that beats any interpretation of the
        prose. This layer hands it over without judging it; choosing is V2's job."""
        stub(serving(page_with(RECIPE_JSONLD)), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert content.structured == [RECIPE_JSONLD]

    async def test_a_page_without_any_is_not_a_failure(self, monkeypatch: MonkeyPatch) -> None:
        stub(serving(PAGE), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert content.structured == []

    async def test_several_blocks_all_come_back(self, monkeypatch: MonkeyPatch) -> None:
        other = {"@type": "WebSite", "name": "A Blog"}
        stub(serving(page_with(other, RECIPE_JSONLD)), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert content.structured == [other, RECIPE_JSONLD]

    async def test_a_block_holding_a_list_is_unwrapped(self, monkeypatch: MonkeyPatch) -> None:
        """A container is not a meaning. Unwrapping the array is not interpreting it."""
        stub(serving(page_with([RECIPE_JSONLD])), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert content.structured == [RECIPE_JSONLD]

    async def test_a_broken_block_is_skipped_rather_than_fatal(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Real sites ship invalid JSON-LD. Losing the page over it helps nobody."""
        stub(serving(page_with("{not json at all", RECIPE_JSONLD)), monkeypatch)
        content = await web.fetch_readable("https://example.com/pancakes")
        assert content.structured == [RECIPE_JSONLD]


class TestWhereItWillNotGo:
    """The URL comes from a user, and the fetch happens on the server's network."""

    @pytest.mark.parametrize(
        "url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", "not a url"]
    )
    async def test_only_the_web_is_fetched(self, url: str) -> None:
        with pytest.raises(AddressNotAllowed):
            await web.fetch_readable(url)

    @pytest.mark.parametrize(
        "address",
        ["127.0.0.1", "::1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254"],
    )
    async def test_the_instance_does_not_fetch_from_its_own_network(
        self, address: str, monkeypatch: MonkeyPatch
    ) -> None:
        """Otherwise a pasted link is a way to read the admin API, or cloud metadata."""
        monkeypatch.setattr(web, "_resolve", lambda host: [address])
        with pytest.raises(AddressNotAllowed):
            await web.fetch_readable("https://sneaky.example.com/x")

    async def test_a_self_hoster_may_allow_their_own_network(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Somebody running a recipe box on their LAN has a real reason to want this."""
        monkeypatch.setenv("QUOOKLY_ALLOW_PRIVATE_FETCH", "true")
        get_settings.cache_clear()
        monkeypatch.setattr(web, "_resolve", lambda host: ["192.168.1.10"])
        stub(serving(PAGE), monkeypatch)
        content = await web.fetch_readable("http://recipes.lan/pancakes")
        assert "225g plain flour" in content.text

    async def test_a_host_that_does_not_resolve_is_refused(self, monkeypatch: MonkeyPatch) -> None:
        def unresolvable(host: str) -> list[str]:
            raise OSError("no such host")

        monkeypatch.setattr(web, "_resolve", unresolvable)
        with pytest.raises(ContentUnreachable):
            await web.fetch_readable("https://nowhere.example.com/x")


class TestRedirects:
    async def test_a_redirect_is_followed(self, monkeypatch: MonkeyPatch) -> None:
        def hop(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/short":
                return httpx.Response(301, headers={"location": "https://example.com/full"})
            return httpx.Response(200, text=PAGE, headers={"content-type": "text/html"})

        stub(hop, monkeypatch)
        content = await web.fetch_readable("https://example.com/short")
        assert content.url == "https://example.com/full"

    async def test_a_redirect_into_the_private_network_is_refused(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """The guard has to hold at every hop. Checking only the pasted URL checks nothing."""
        resolutions = {"example.com": ["93.184.216.34"], "internal": ["127.0.0.1"]}
        monkeypatch.setattr(web, "_resolve", lambda host: resolutions[host])

        def redirect(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "http://internal/admin"})

        stub(redirect, monkeypatch)
        with pytest.raises(AddressNotAllowed):
            await web.fetch_readable("https://example.com/short")

    async def test_a_redirect_loop_ends(self, monkeypatch: MonkeyPatch) -> None:
        def circle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://example.com/again"})

        stub(circle, monkeypatch)
        with pytest.raises(ContentUnreachable):
            await web.fetch_readable("https://example.com/again")


class TestWhenItGoesWrong:
    async def test_a_missing_page_is_reported(self, monkeypatch: MonkeyPatch) -> None:
        stub(serving("gone", status=404), monkeypatch)
        with pytest.raises(ContentUnreachable):
            await web.fetch_readable("https://example.com/gone")

    async def test_a_site_that_blocks_readers_is_told_apart_from_a_broken_one(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Several large recipe publishers answer 403 to anything without a browser
        fingerprint. The page works in the cook's own browser, and saying so is more use
        than reporting a failure they cannot reproduce."""
        stub(serving("nope", status=403), monkeypatch)
        with pytest.raises(ContentRefused):
            await web.fetch_readable("https://example.com/guarded")

    async def test_rate_limiting_is_the_same_kind_of_answer(self, monkeypatch: MonkeyPatch) -> None:
        stub(serving("slow down", status=429), monkeypatch)
        with pytest.raises(ContentRefused):
            await web.fetch_readable("https://example.com/busy")

    async def test_an_unreachable_host_is_reported(self, monkeypatch: MonkeyPatch) -> None:
        def refuse(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        stub(refuse, monkeypatch)
        with pytest.raises(ContentUnreachable):
            await web.fetch_readable("https://example.com/x")

    async def test_something_that_is_not_a_page_is_refused(self, monkeypatch: MonkeyPatch) -> None:
        """A PDF or a video is not a thing this can read, and downloading one to find out
        that it is not is a waste of somebody's bandwidth."""
        stub(serving("%PDF-1.4", content_type="application/pdf"), monkeypatch)
        with pytest.raises(ContentUnreadable):
            await web.fetch_readable("https://example.com/recipe.pdf")

    async def test_an_enormous_page_is_refused(self, monkeypatch: MonkeyPatch) -> None:
        """A URL is a user input, and a server that downloads whatever length it is told
        has handed out a way to exhaust its own memory."""
        stub(serving("<html><body>" + "x" * (web.MAXIMUM_BYTES + 1)), monkeypatch)
        with pytest.raises(ContentUnreadable):
            await web.fetch_readable("https://example.com/huge")
