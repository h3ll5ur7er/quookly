"""Storing a recipe's prose in another language (ADR-032, ADR-064).

The decision this module holds up: **a translation records what it translated**. Not a
`stale` flag — a flag has to be set by everything that edits a recipe, and the failure is
silent when somebody adds the next write path. A fingerprint of the source travels with
the translation, and one whose fingerprint no longer matches is simply not returned.

Invalidation by construction rather than by remembering. Editing a recipe needs to know
nothing about translations, which is the only way that stays correct.
"""

from hashlib import sha256

from sqlmodel import col, delete, select

from quookly.access.database import session
from quookly.access.models import RecipeTranslationRow, RecipeTranslationStepRow
from quookly.contracts.translation import HeldTranslation, Translatable


def fingerprint(prose: Translatable) -> str:
    """What a translation was a translation of, in one short string.

    Every part of the prose, separated by something no prose contains, so that moving a
    sentence from the summary into a step changes the answer. A hash rather than the text
    itself because it is compared, never read.
    """
    parts = [prose.title, prose.summary or "", *prose.steps]
    return sha256("\x00".join(parts).encode()).hexdigest()


async def keep(
    recipe_id: int,
    locale: str,
    words: Translatable,
    *,
    of: Translatable,
    by_hand: bool = False,
) -> None:
    """Store one translation, replacing whatever was held for that language.

    Replacing rather than adding: a recipe has one translation per language, and keeping
    the previous one would be keeping a translation of words that have moved on.
    """
    async with session() as active:
        held = (
            await active.exec(
                select(RecipeTranslationRow).where(
                    col(RecipeTranslationRow.recipe_id) == recipe_id,
                    col(RecipeTranslationRow.locale) == locale,
                )
            )
        ).first()
        if held is not None and held.id is not None:
            await active.exec(
                delete(RecipeTranslationStepRow).where(
                    col(RecipeTranslationStepRow.translation_id) == held.id
                )
            )
            await active.delete(held)
            await active.flush()

        row = RecipeTranslationRow(
            recipe_id=recipe_id,
            locale=locale,
            title=words.title,
            summary=words.summary,
            source_fingerprint=fingerprint(of),
            by_hand=by_hand,
        )
        active.add(row)
        await active.flush()
        assert row.id is not None
        for position, instruction in enumerate(words.steps):
            active.add(
                RecipeTranslationStepRow(
                    translation_id=row.id, position=position, instruction=instruction
                )
            )
        await active.commit()


async def held(recipe_id: int, locale: str, *, of: Translatable) -> HeldTranslation | None:
    """The translation of *these words*, or nothing.

    `of` is not a filter on the caller's behalf — it is the whole mechanism. A translation
    of words that have since changed is not stale, it is a wrong instruction, and a cook
    can be burned by one (ADR-064).
    """
    wanted = fingerprint(of)
    async with session() as active:
        row = (
            await active.exec(
                select(RecipeTranslationRow).where(
                    col(RecipeTranslationRow.recipe_id) == recipe_id,
                    col(RecipeTranslationRow.locale) == locale,
                    col(RecipeTranslationRow.source_fingerprint) == wanted,
                )
            )
        ).first()
        if row is None or row.id is None:
            return None

        steps = (
            await active.exec(
                select(RecipeTranslationStepRow)
                .where(col(RecipeTranslationStepRow.translation_id) == row.id)
                .order_by(col(RecipeTranslationStepRow.position))
            )
        ).all()

    return HeldTranslation(
        words=Translatable(
            title=row.title,
            summary=row.summary,
            steps=[one.instruction for one in steps],
        ),
        by_hand=row.by_hand,
    )


async def written_by_hand(recipe_id: int) -> list[str]:
    """The languages somebody here has written a translation in, current or not.

    What an export carries and what a screen offers to bring back up to date. A model's
    translation is nobody's work and is left out of both (ADR-064).
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(RecipeTranslationRow).where(
                    col(RecipeTranslationRow.recipe_id) == recipe_id,
                    col(RecipeTranslationRow.by_hand).is_(True),
                )
            )
        ).all()
    return sorted(row.locale for row in rows)
