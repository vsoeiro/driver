"""add metadata_filters to metadata_rules

Revision ID: d2b7c4a91e6f
Revises: c7f4e9a2d1b3
Create Date: 2026-03-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2b7c4a91e6f"
down_revision: Union[str, Sequence[str], None] = "c7f4e9a2d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("metadata_rules") as batch_op:
        batch_op.add_column(
            sa.Column("metadata_filters", sa.JSON(), nullable=False, server_default="[]")
        )

    with op.batch_alter_table("metadata_rules") as batch_op:
        batch_op.alter_column("metadata_filters", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("metadata_rules") as batch_op:
        batch_op.drop_column("metadata_filters")
