"""observability_versioning_and_rules

Revision ID: 8f7d2e1c9a11
Revises: 4f2e0f7861d4
Create Date: 2026-02-16 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f7d2e1c9a11"
down_revision: Union[str, Sequence[str], None] = "4f2e0f7861d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- jobs observability/retry/dead-letter ---
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))
        batch_op.add_column(sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("progress_total", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("metrics", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("dead_letter_reason", sa.Text(), nullable=True))

    # Remove temporary server defaults
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.alter_column("max_retries", server_default=None)
        batch_op.alter_column("progress_current", server_default=None)
        batch_op.alter_column("progress_percent", server_default=None)

    # --- metadata dedupe + versioning ---
    with op.batch_alter_table("item_metadata") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    # Keep only one metadata row per (account_id, item_id), preserving most recently updated.
    op.execute(
        """
        DELETE FROM item_metadata
        WHERE id IN (
            SELECT id FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY account_id, item_id
                        ORDER BY updated_at DESC, id DESC
                    ) AS rn
                FROM item_metadata
            ) ranked
            WHERE ranked.rn > 1
        )
        """
    )

    with op.batch_alter_table("item_metadata") as batch_op:
        batch_op.create_unique_constraint(
            "uq_item_metadata_account_item",
            ["account_id", "item_id"],
        )
        batch_op.alter_column("version", server_default=None)

    op.create_table(
        "item_metadata_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("metadata_id", sa.UUID(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("previous_category_id", sa.UUID(), nullable=True),
        sa.Column("previous_values", sa.JSON(), nullable=True),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("new_category_id", sa.UUID(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.Column("new_version", sa.Integer(), nullable=True),
        sa.Column("batch_id", sa.UUID(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["metadata_id"], ["item_metadata.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- automatic metadata rules ---
    op.create_table(
        "metadata_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("path_contains", sa.String(length=500), nullable=True),
        sa.Column("path_prefix", sa.String(length=1000), nullable=True),
        sa.Column("target_category_id", sa.UUID(), nullable=False),
        sa.Column("target_values", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("include_folders", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["linked_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_category_id"], ["metadata_categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("metadata_rules")
    op.drop_table("item_metadata_history")

    with op.batch_alter_table("item_metadata") as batch_op:
        batch_op.drop_constraint("uq_item_metadata_account_item", type_="unique")
        batch_op.drop_column("version")

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("dead_letter_reason")
        batch_op.drop_column("dead_lettered_at")
        batch_op.drop_column("last_error")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("metrics")
        batch_op.drop_column("progress_percent")
        batch_op.drop_column("progress_total")
        batch_op.drop_column("progress_current")
        batch_op.drop_column("max_retries")
