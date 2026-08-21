"""Refresh the captured page corpus.

Run by hand, not by the test suite — the suite must not need the network, and these
fixtures are meant to be a fixed point that a change to the reader is measured against.

    cd backend && uv run python tests/fixtures/capture.py

The metadata blocks are kept, and the readable text with them — a page that publishes no
metadata is read out of its prose, and a fixture without the prose could not exercise that
half. The page *markup* is still thrown away: it is the part being read around, and four
megabytes of it would be keeping the wrong thing. A test failing after a refresh is real
news about how a site has changed, not a broken test.
"""

import asyncio
import json
from pathlib import Path

from quookly.access import web

OUT = Path("tests/fixtures/pages")
PAGES = {
    "bbcgoodfood-classic-pancakes": "https://www.bbcgoodfood.com/recipes/classic-pancakes",
    "bbcgoodfood-chocolate-brownies": "https://www.bbcgoodfood.com/recipes/best-ever-chocolate-brownies-recipe",
    "allrecipes-old-fashioned-pancakes": "https://www.allrecipes.com/recipe/21014/good-old-fashioned-pancakes/",
    "jamieoliver-easy-pancakes": "https://www.jamieoliver.com/recipes/eggs/easy-pancakes/",
    # Reported by a cook, and both awkward in their own way: the first writes its
    # ingredient notes in brackets and its ginger as "4-inch piece", the second is a
    # French blog from 2005.
    "woksoflife-hainanese-chicken-rice": "https://thewoksoflife.com/hainanese-chicken-rice/",
    "papilles-quiche-lorraine": "https://www.papillesetpupilles.fr/2005/07/quiche-lorraine.html/",
}


async def main() -> None:
    for name, url in PAGES.items():
        try:
            content = await web.fetch_readable(url)
        except Exception as failure:
            print(f"{name}: FAILED {failure}")
            continue
        (OUT / f"{name}.json").write_text(
            json.dumps(
                {
                    "url": content.url,
                    "title": content.title,
                    "text": content.text,
                    "structured": content.structured,
                },
                indent=1,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"{name}: {len(content.structured)} blocks")


asyncio.run(main())
