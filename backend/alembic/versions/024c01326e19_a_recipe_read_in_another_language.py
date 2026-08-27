"""a recipe read in another language

Prose only. Quantities, durations and temperatures are columns rendered per cook, and
ingredient names resolve through the registry per locale — so a translation cannot change
what a recipe asks for, and no verdict is affected (ADR-006, ADR-032).

`source_fingerprint` is what makes invalidation automatic. A translation records what it
translated, and one whose fingerprint no longer matches the recipe is not used — rather
than a `stale` flag that every future write path would have to remember to set (ADR-064).

Revision ID: 024c01326e19
Revises: 4705ba7d6af6
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

revision: str = "024c01326e19"
down_revision: str | None = "4705ba7d6af6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_translation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("locale", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_fingerprint", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("by_hand", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recipe_id", "locale", name="uq_recipe_translation"),
    )
    op.create_index(op.f("ix_recipe_translation_recipe_id"), "recipe_translation", ["recipe_id"])
    op.create_index(op.f("ix_recipe_translation_locale"), "recipe_translation", ["locale"])
    op.create_index(
        op.f("ix_recipe_translation_source_fingerprint"),
        "recipe_translation",
        ["source_fingerprint"],
    )

    op.create_table(
        "recipe_translation_step",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("translation_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("instruction", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["translation_id"], ["recipe_translation.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("translation_id", "position", name="uq_recipe_translation_step"),
    )
    op.create_index(
        op.f("ix_recipe_translation_step_translation_id"),
        "recipe_translation_step",
        ["translation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_recipe_translation_step_translation_id"), table_name="recipe_translation_step"
    )
    op.drop_table("recipe_translation_step")
    op.drop_index(op.f("ix_recipe_translation_source_fingerprint"), table_name="recipe_translation")
    op.drop_index(op.f("ix_recipe_translation_locale"), table_name="recipe_translation")
    op.drop_index(op.f("ix_recipe_translation_recipe_id"), table_name="recipe_translation")
    op.drop_table("recipe_translation")
