"""The recipe index, and asking it questions (V10).

Retrieval is kept apart from ranking on purpose: the index technology and the ranking
policy change for entirely different reasons and at entirely different rates. This service
knows how to find candidates; what order they belong in is `RankingEngine`'s.

SQLite FTS5, which ADR-009 named as the mechanism and as the place the SQLite decision will
strain first. Nothing above this module knows that — a caller asks for recipes matching some
words and gets ids and scores back.
"""

import re
from decimal import Decimal

from sqlalchemy import text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.models import (
    IngredientLineRow,
    IngredientNameRow,
    IngredientRow,
    RecipeRow,
)
from quookly.contracts.search import Hit
from quookly.utilities.diagnostics import get_logger

log = get_logger("search")

#: What a word is, for the purpose of searching. Everything else a cook might type — the
#: quotes, brackets and asterisks that mean something to FTS5's own query language — is
#: dropped rather than escaped, because a search box is a place to type words and an error
#: message about syntax would be a strange thing to hand somebody looking for a pancake.
_WORDS = re.compile(r"\w+", re.UNICODE)

#: How much each column counts. A title is what a recipe *is*; the ingredients are what a
#: cook has and is looking to use; the summary is prose around both. The weights are
#: positional and include the unindexed columns, which take none.
_WEIGHTS = "0.0, 0.0, 10.0, 4.0, 1.0"


def phrase(written: str) -> str | None:
    """A cook's words as a query FTS5 will accept, or nothing where there are none.

    Every word must appear, and the last one may still be half-typed — "panc" finds
    pancakes, which is what a search box that answers as you type has to do.
    """
    words = _WORDS.findall(written.lower())
    if not words:
        return None
    *rest, last = words
    return " AND ".join([*(f'"{word}"' for word in rest), f'"{last}"*'])


async def _names_for(active: AsyncSession, recipe_ids: list[int]) -> dict[int, list[str]]:
    """Every name every ingredient of these recipes goes by, in every language known.

    All of them, not the cook's own: a Swiss household reads the app in German and copies
    recipes titled in English, and "Mehl" should find the pancakes either way. The index is
    one place where mixing languages is the right answer rather than the confusion V14
    exists to prevent.
    """
    rows = (
        await active.exec(
            select(IngredientLineRow.recipe_id, IngredientNameRow.name)
            .join(IngredientRow, col(IngredientLineRow.ingredient_id) == col(IngredientRow.id))
            .join(IngredientNameRow, col(IngredientNameRow.ingredient_id) == col(IngredientRow.id))
            .where(col(IngredientLineRow.recipe_id).in_(recipe_ids))
        )
    ).all()

    gathered: dict[int, list[str]] = {}
    for recipe_id, name in rows:
        held = gathered.setdefault(recipe_id, [])
        if name not in held:
            held.append(name)
    return gathered


async def _write(active: AsyncSession, row: RecipeRow, names: list[str]) -> None:
    await active.execute(
        text("DELETE FROM recipe_search WHERE recipe_id = :recipe_id"),
        {"recipe_id": row.id},
    )
    await active.execute(
        text(
            "INSERT INTO recipe_search (recipe_id, cook_id, title, ingredients, summary)"
            " VALUES (:recipe_id, :cook_id, :title, :ingredients, :summary)"
        ),
        {
            "recipe_id": row.id,
            "cook_id": row.cook_id,
            "title": row.title,
            "ingredients": ", ".join(names),
            "summary": row.summary or "",
        },
    )


async def index_recipe(recipe_id: int) -> None:
    """Put one recipe in the index, replacing whatever was there for it."""
    async with session() as active:
        row = await active.get(RecipeRow, recipe_id)
        if row is None or row.id is None:
            return
        await _write(active, row, (await _names_for(active, [row.id])).get(row.id, []))
        await active.commit()


async def remove(recipe_id: int) -> None:
    """Take a recipe out of the index. A hit on a recipe that is gone is worse than a miss."""
    async with session() as active:
        await active.execute(
            text("DELETE FROM recipe_search WHERE recipe_id = :recipe_id"),
            {"recipe_id": recipe_id},
        )
        await active.commit()


async def reindex() -> int:
    """Build the whole index from what is stored. Returns how many recipes went in.

    Run at start-up. The index is **derived**, so it cannot be the source of truth and does
    not need to be treated as one: rebuilding is cheap at household scale and it means an
    upgrade that changes what is indexed needs no migration, no version marker, and no way
    to be half-applied.

    Three queries whatever the size of the collection, because a per-recipe fetch here
    would be the slowest thing an instance does on the way up.
    """
    async with session() as active:
        rows = (await active.exec(select(RecipeRow))).all()
        ids = [row.id for row in rows if row.id is not None]
        if not ids:
            await active.execute(text("DELETE FROM recipe_search"))
            await active.commit()
            return 0

        names = await _names_for(active, ids)
        await active.execute(text("DELETE FROM recipe_search"))
        for row in rows:
            if row.id is not None:
                await _write(active, row, names.get(row.id, []))
        await active.commit()

    log.info("indexed %s recipes for search", len(ids), extra={"recipes": len(ids)})
    return len(ids)


async def query(written: str, cook_id: int, limit: int = 50) -> list[Hit]:
    """Recipes matching these words, best first (UC-3.1).

    Scored by BM25 and handed on unranked in any deeper sense: pantry coverage, expiry and
    suitability are ranking policy, and they belong to the engine rather than to the index.
    """
    matching = phrase(written)
    if matching is None:
        return []

    async with session() as active:
        rows = (
            await active.execute(
                text(
                    f"SELECT recipe_id, bm25(recipe_search, {_WEIGHTS}) AS score"
                    " FROM recipe_search"
                    " WHERE recipe_search MATCH :matching AND cook_id = :cook_id"
                    " ORDER BY score LIMIT :limit"
                ),
                {"matching": matching, "cook_id": cook_id, "limit": limit},
            )
        ).all()

    # BM25 in SQLite is negative, and more negative is better. Turned round here so that
    # nothing above this module has to know one implementation's convention.
    return [Hit(recipe_id=int(row[0]), score=Decimal(str(-row[1]))) for row in rows]
