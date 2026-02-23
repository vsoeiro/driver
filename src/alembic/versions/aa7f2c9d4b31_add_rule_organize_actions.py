"""add rule organize actions

Revision ID: aa7f2c9d4b31
Revises: c9e4a1b2d3f4
Create Date: 2026-02-18 00:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "aa7f2c9d4b31"
down_revision: Union[str, Sequence[str], None] = "c9e4a1b2d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("metadata_rules", sa.Column("apply_metadata", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("metadata_rules", sa.Column("apply_rename", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("metadata_rules", sa.Column("rename_template", sa.String(length=500), nullable=True))
    op.add_column("metadata_rules", sa.Column("apply_move", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("metadata_rules", sa.Column("destination_account_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("metadata_rules", sa.Column("destination_folder_id", sa.String(length=255), nullable=True))
    op.add_column("metadata_rules", sa.Column("destination_path_template", sa.String(length=1000), nullable=True))
    op.create_foreign_key(
        "fk_metadata_rules_destination_account_id_linked_accounts",
        "metadata_rules",
        "linked_accounts",
        ["destination_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("UPDATE metadata_rules SET destination_folder_id = 'root' WHERE destination_folder_id IS NULL")
    op.alter_column("metadata_rules", "destination_folder_id", server_default=sa.text("'root'"))
    op.alter_column("metadata_rules", "apply_metadata", server_default=None)
    op.alter_column("metadata_rules", "apply_rename", server_default=None)
    op.alter_column("metadata_rules", "apply_move", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_metadata_rules_destination_account_id_linked_accounts", "metadata_rules", type_="foreignkey")
    op.drop_column("metadata_rules", "destination_path_template")
    op.drop_column("metadata_rules", "destination_folder_id")
    op.drop_column("metadata_rules", "destination_account_id")
    op.drop_column("metadata_rules", "apply_move")
    op.drop_column("metadata_rules", "rename_template")
    op.drop_column("metadata_rules", "apply_rename")
    op.drop_column("metadata_rules", "apply_metadata")
