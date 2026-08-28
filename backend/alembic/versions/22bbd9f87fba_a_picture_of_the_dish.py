"""a picture of the dish

One picture per recipe, as two columns rather than a table. The Academy needs several per
page because a technique is shown in stages; a dish is one photograph, and a table for it
would be machinery for a cardinality nothing asks for.

Both columns or neither: a media id without alt text is a picture some readers do not get,
and this project checks accessibility as it builds rather than retrofitting it.

Revision ID: 22bbd9f87fba
Revises: 024c01326e19
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

revision: str = "22bbd9f87fba"
down_revision: str | None = "024c01326e19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recipe", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("picture_media_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("picture_description", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("recipe", schema=None) as batch_op:
        batch_op.drop_column("picture_description")
        batch_op.drop_column("picture_media_id")
