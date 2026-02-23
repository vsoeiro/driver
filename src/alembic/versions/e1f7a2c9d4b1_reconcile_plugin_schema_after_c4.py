"""reconcile_plugin_schema_after_c4

Revision ID: e1f7a2c9d4b1
Revises: c4a6f8f1d2e3
Create Date: 2026-02-16 14:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f7a2c9d4b1"
down_revision: Union[str, Sequence[str], None] = "c4a6f8f1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "metadata_categories"):
        if not _has_column(inspector, "metadata_categories", "is_active"):
            op.add_column(
                "metadata_categories",
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            )
        if not _has_column(inspector, "metadata_categories", "managed_by_plugin"):
            op.add_column(
                "metadata_categories",
                sa.Column("managed_by_plugin", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        if not _has_column(inspector, "metadata_categories", "plugin_key"):
            op.add_column("metadata_categories", sa.Column("plugin_key", sa.String(length=80), nullable=True))
        if not _has_column(inspector, "metadata_categories", "is_locked"):
            op.add_column(
                "metadata_categories",
                sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "metadata_attributes"):
        if not _has_column(inspector, "metadata_attributes", "managed_by_plugin"):
            op.add_column(
                "metadata_attributes",
                sa.Column("managed_by_plugin", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        if not _has_column(inspector, "metadata_attributes", "plugin_key"):
            op.add_column("metadata_attributes", sa.Column("plugin_key", sa.String(length=80), nullable=True))
        if not _has_column(inspector, "metadata_attributes", "plugin_field_key"):
            op.add_column("metadata_attributes", sa.Column("plugin_field_key", sa.String(length=80), nullable=True))
        if not _has_column(inspector, "metadata_attributes", "is_locked"):
            op.add_column(
                "metadata_attributes",
                sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "metadata_plugins"):
        op.create_table(
            "metadata_plugins",
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("category_id", sa.UUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["category_id"], ["metadata_categories.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("key"),
        )


def downgrade() -> None:
    # Best-effort reverse for the reconciliation migration.
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "metadata_plugins"):
        op.drop_table("metadata_plugins")
