"""add_metadata_query_indexes

Revision ID: 3e6a5b1c4d20
Revises: 2d84c79ab8d3
Create Date: 2026-02-23 10:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3e6a5b1c4d20"
down_revision: Union[str, Sequence[str], None] = "2d84c79ab8d3"
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
    # Item metadata lookups for items list + series summary.
    _create_index_if_missing(
        "item_metadata",
        "ix_item_metadata_category_account_item",
        ["category_id", "account_id", "item_id"],
    )
    _create_index_if_missing(
        "item_metadata",
        "ix_item_metadata_account_category",
        ["account_id", "category_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    _drop_index_if_exists("item_metadata", "ix_item_metadata_account_category")
    _drop_index_if_exists("item_metadata", "ix_item_metadata_category_account_item")
