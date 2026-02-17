"""reconcile_items_table

Revision ID: f2c7b8d91a4e
Revises: e1f7a2c9d4b1
Create Date: 2026-02-16 20:22:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2c7b8d91a4e"
down_revision: Union[str, Sequence[str], None] = "e1f7a2c9d4b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "items"):
        return

    op.create_table(
        "items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=True),
        sa.Column("item_type", sa.String(length=50), nullable=False, server_default="file"),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("extension", sa.String(length=50), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["linked_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "item_id", name="uq_items_account_item"),
    )

    op.create_index("ix_items_account_id", "items", ["account_id"], unique=False)
    op.create_index("ix_items_parent_id", "items", ["parent_id"], unique=False)
    op.create_index("ix_items_path", "items", ["path"], unique=False)
    op.create_index("ix_items_extension", "items", ["extension"], unique=False)
    op.create_index("ix_items_item_type", "items", ["item_type"], unique=False)
    op.create_index("ix_items_modified_at", "items", ["modified_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, "items"):
        return

    op.drop_index("ix_items_modified_at", table_name="items")
    op.drop_index("ix_items_item_type", table_name="items")
    op.drop_index("ix_items_extension", table_name="items")
    op.drop_index("ix_items_path", table_name="items")
    op.drop_index("ix_items_parent_id", table_name="items")
    op.drop_index("ix_items_account_id", table_name="items")
    op.drop_table("items")
