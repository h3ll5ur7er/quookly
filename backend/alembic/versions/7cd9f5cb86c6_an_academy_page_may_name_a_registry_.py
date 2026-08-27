"""an academy page may name a registry entry

Nullable, and absent for every page that exists: they are all about techniques, and a
technique is not an ingredient. Set for pages of kind `ingredient`, which show the entry's
facts by reading them rather than by holding a copy (ADR-061).

A real foreign key rather than a slug, unlike `eater_constraint.ingredient_slug`. The
reasoning there was that avoiding coriander should work whether or not the registry has
heard of it; here the opposite is true — a page about an ingredient nobody can put in a
recipe is a page about nothing, and the constraint is what says so.

Revision ID: 7cd9f5cb86c6
Revises: 35a3e6292dd2
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7cd9f5cb86c6"
down_revision: str | None = "35a3e6292dd2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("academy_page", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ingredient_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_academy_page_ingredient_id"), ["ingredient_id"])
        batch_op.create_foreign_key(
            "fk_academy_page_ingredient_id_ingredient", "ingredient", ["ingredient_id"], ["id"]
        )
        # The section enum gained a member, which widens the column SQLite stores it in.
        # Stated rather than left implicit: the migrations and the models are checked
        # against each other, and a silent type drift is a failing test later.
        batch_op.alter_column(
            "kind",
            existing_type=sa.VARCHAR(length=9),
            type_=sa.Enum("TECHNIQUE", "INGREDIENT", name="pagekind"),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("academy_page", schema=None) as batch_op:
        batch_op.drop_constraint("fk_academy_page_ingredient_id_ingredient", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_academy_page_ingredient_id"))
        batch_op.alter_column(
            "kind",
            existing_type=sa.Enum("TECHNIQUE", "INGREDIENT", name="pagekind"),
            type_=sa.VARCHAR(length=9),
            existing_nullable=False,
        )
        batch_op.drop_column("ingredient_id")
