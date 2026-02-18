"""Add ai_suggestions field to item_metadata.

Revision ID: c9e4a1b2d3f4
Revises: b8f1d2a3c4e5
Create Date: 2026-02-17 12:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9e4a1b2d3f4"
down_revision: Union[str, None] = "b8f1d2a3c4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_metadata",
        sa.Column("ai_suggestions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("item_metadata", "ai_suggestions", server_default=None)


def downgrade() -> None:
    op.drop_column("item_metadata", "ai_suggestions")

