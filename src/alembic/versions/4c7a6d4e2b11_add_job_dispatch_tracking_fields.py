"""Add job dispatch tracking fields.

Revision ID: 4c7a6d4e2b11
Revises: d2b7c4a91e6f
Create Date: 2026-03-21 17:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c7a6d4e2b11"
down_revision: Union[str, Sequence[str], None] = "d2b7c4a91e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("queue_enqueued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("queue_dispatch_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("jobs", sa.Column("queue_last_error", sa.Text(), nullable=True))
    op.alter_column("jobs", "queue_dispatch_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("jobs", "queue_last_error")
    op.drop_column("jobs", "queue_dispatch_attempts")
    op.drop_column("jobs", "queue_enqueued_at")
