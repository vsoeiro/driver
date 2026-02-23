"""drop item metadata suggestions column

Revision ID: 862c4c452b43
Revises: aa7f2c9d4b31
Create Date: 2026-02-21 22:45:02.093430

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '862c4c452b43'
down_revision: Union[str, Sequence[str], None] = 'aa7f2c9d4b31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("item_metadata")}
    if "ai_suggestions" in columns:
        op.drop_column("item_metadata", "ai_suggestions")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("item_metadata")}
    if "ai_suggestions" not in columns:
        op.add_column(
            "item_metadata",
            sa.Column("ai_suggestions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )
        op.alter_column("item_metadata", "ai_suggestions", server_default=None)
