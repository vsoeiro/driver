"""add apply_remove_metadata to metadata_rules

Revision ID: c7f4e9a2d1b3
Revises: 7b2e9c1a4f77
Create Date: 2026-03-01 00:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7f4e9a2d1b3"
down_revision: Union[str, Sequence[str], None] = "7b2e9c1a4f77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "metadata_rules",
        sa.Column(
            "apply_remove_metadata",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column("metadata_rules", "apply_remove_metadata", server_default=None)


def downgrade() -> None:
    op.drop_column("metadata_rules", "apply_remove_metadata")

