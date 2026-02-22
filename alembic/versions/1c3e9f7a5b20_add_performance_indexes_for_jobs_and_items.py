"""add_performance_indexes_for_jobs_and_items

Revision ID: 1c3e9f7a5b20
Revises: 9a2f71d4c6b8
Create Date: 2026-02-22 11:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c3e9f7a5b20"
down_revision: Union[str, Sequence[str], None] = "9a2f71d4c6b8"
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
    # Jobs table: frequent filters and ordering on status/timestamps.
    _create_index_if_missing("jobs", "ix_jobs_status_created_at", ["status", "created_at"])
    _create_index_if_missing("jobs", "ix_jobs_status_next_retry_at", ["status", "next_retry_at"])
    _create_index_if_missing("jobs", "ix_jobs_status_started_at", ["status", "started_at"])
    _create_index_if_missing("jobs", "ix_jobs_dead_lettered_at", ["dead_lettered_at"])
    _create_index_if_missing("jobs", "ix_jobs_completed_at", ["completed_at"])
    _create_index_if_missing("jobs", "ix_jobs_type_created_at", ["type", "created_at"])

    # Items table: list/filter/sort paths used by library and metadata flows.
    _create_index_if_missing(
        "items",
        "ix_items_account_item_type_modified_at",
        ["account_id", "item_type", "modified_at"],
    )
    _create_index_if_missing("items", "ix_items_account_extension", ["account_id", "extension"])
    _create_index_if_missing("items", "ix_items_account_path", ["account_id", "path"])


def downgrade() -> None:
    """Downgrade schema."""
    _drop_index_if_exists("items", "ix_items_account_path")
    _drop_index_if_exists("items", "ix_items_account_extension")
    _drop_index_if_exists("items", "ix_items_account_item_type_modified_at")

    _drop_index_if_exists("jobs", "ix_jobs_type_created_at")
    _drop_index_if_exists("jobs", "ix_jobs_completed_at")
    _drop_index_if_exists("jobs", "ix_jobs_dead_lettered_at")
    _drop_index_if_exists("jobs", "ix_jobs_status_started_at")
    _drop_index_if_exists("jobs", "ix_jobs_status_next_retry_at")
    _drop_index_if_exists("jobs", "ix_jobs_status_created_at")
