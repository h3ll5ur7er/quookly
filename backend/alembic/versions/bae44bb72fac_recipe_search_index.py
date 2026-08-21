"""recipe search index

A full-text index over recipes, as an SQLite FTS5 virtual table. Written by hand because
alembic cannot autogenerate a virtual table and would try to drop this one on every
subsequent revision if it could see it.

Its columns are chosen for what a cook types. Titles matter most, then the ingredients —
"what can I do with rhubarb" is a question about ingredients, not about titles — and the
summary least. Steps are left out on purpose: every recipe's method mentions its
ingredients, so indexing them would make every search match everything.

`remove_diacritics 2` so that "creme" finds "Crème brûlée" and "puree" finds "purée". A
cook typing on a phone keyboard should not have to find the accent first.

Revision ID: bae44bb72fac
Revises: 26a476b10780
Create Date: 2026-08-22 00:38:49
"""

from collections.abc import Sequence

from alembic import op

revision: str = "bae44bb72fac"
down_revision: str | None = "26a476b10780"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE recipe_search USING fts5(
            recipe_id UNINDEXED,
            cook_id UNINDEXED,
            title,
            ingredients,
            summary,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE recipe_search")
