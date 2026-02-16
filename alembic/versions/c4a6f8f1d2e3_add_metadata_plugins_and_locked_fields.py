"""add_metadata_plugins_and_locked_fields

Revision ID: c4a6f8f1d2e3
Revises: b1d4b8f3c2a1
Create Date: 2026-02-16 12:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4a6f8f1d2e3"
down_revision: Union[str, Sequence[str], None] = "b1d4b8f3c2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("metadata_categories", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    op.add_column("metadata_categories", sa.Column("managed_by_plugin", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("metadata_categories", sa.Column("plugin_key", sa.String(length=80), nullable=True))
    op.add_column("metadata_categories", sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.add_column("metadata_attributes", sa.Column("managed_by_plugin", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("metadata_attributes", sa.Column("plugin_key", sa.String(length=80), nullable=True))
    op.add_column("metadata_attributes", sa.Column("plugin_field_key", sa.String(length=80), nullable=True))
    op.add_column("metadata_attributes", sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.create_table(
        "metadata_plugins",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["metadata_categories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )

    op.execute("DROP TABLE IF EXISTS comic_assets")


def downgrade() -> None:
    op.drop_table("metadata_plugins")

    op.drop_column("metadata_attributes", "is_locked")
    op.drop_column("metadata_attributes", "plugin_field_key")
    op.drop_column("metadata_attributes", "plugin_key")
    op.drop_column("metadata_attributes", "managed_by_plugin")

    op.drop_column("metadata_categories", "is_locked")
    op.drop_column("metadata_categories", "plugin_key")
    op.drop_column("metadata_categories", "managed_by_plugin")
    op.drop_column("metadata_categories", "is_active")
