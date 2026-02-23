"""add_app_settings_table

Revision ID: b1d4b8f3c2a1
Revises: 8f7d2e1c9a11
Create Date: 2026-02-16 23:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1d4b8f3c2a1"
down_revision: Union[str, Sequence[str], None] = "8f7d2e1c9a11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO app_settings ("key", "value", "description", "updated_at")
            VALUES
              ('enable_daily_sync_scheduler', 'true', 'Enable/disable the automatic daily sync scheduler.', CURRENT_TIMESTAMP),
              ('daily_sync_cron', '0 0 * * *', 'Cron expression (5 fields) for scheduler frequency.', CURRENT_TIMESTAMP)
            """
        )
    )


def downgrade() -> None:
    op.drop_table("app_settings")
