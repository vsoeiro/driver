"""add_phase2_indexes_and_pg_trgm

Revision ID: 6f4d2c8b9a10
Revises: 3e6a5b1c4d20
Create Date: 2026-02-24 14:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f4d2c8b9a10"
down_revision: Union[str, Sequence[str], None] = "3e6a5b1c4d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _index_exists(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _index_exists(inspector, table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    """Upgrade schema."""
    _create_index_if_missing("jobs", "ix_jobs_dedupe_status", ["dedupe_key", "status"])
    _create_index_if_missing("item_metadata", "ix_item_metadata_category_id", ["category_id"])
    _create_index_if_missing("item_metadata", "ix_item_metadata_updated_at", ["updated_at"])
    _create_index_if_missing("items", "ix_items_account_item_type", ["account_id", "item_type"])
    _create_index_if_missing("items", "ix_items_account_modified_at", ["account_id", "modified_at"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_items_path_trgm ON items USING gin (lower(path) gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_items_name_trgm ON items USING gin (lower(name) gin_trgm_ops)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_items_name_trgm")
        op.execute("DROP INDEX IF EXISTS ix_items_path_trgm")

    _drop_index_if_exists("items", "ix_items_account_modified_at")
    _drop_index_if_exists("items", "ix_items_account_item_type")
    _drop_index_if_exists("item_metadata", "ix_item_metadata_updated_at")
    _drop_index_if_exists("item_metadata", "ix_item_metadata_category_id")
    _drop_index_if_exists("jobs", "ix_jobs_dedupe_status")
