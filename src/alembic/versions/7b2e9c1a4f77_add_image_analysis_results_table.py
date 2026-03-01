"""add_image_analysis_results_table

Revision ID: 7b2e9c1a4f77
Revises: 5a1c0ee9d2ab
Create Date: 2026-02-27 16:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b2e9c1a4f77"
down_revision: Union[str, Sequence[str], None] = "5a1c0ee9d2ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_analysis_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
        sa.Column("suggested_category", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("detected_objects", sa.JSON(), nullable=True),
        sa.Column("entities", sa.JSON(), nullable=True),
        sa.Column("technical_metadata", sa.JSON(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(length=120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "item_id",
            name="uq_image_analysis_results_account_item",
        ),
    )
    op.create_index(
        "ix_image_analysis_results_status",
        "image_analysis_results",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_image_analysis_results_updated_at",
        "image_analysis_results",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_image_analysis_results_updated_at", table_name="image_analysis_results")
    op.drop_index("ix_image_analysis_results_status", table_name="image_analysis_results")
    op.drop_table("image_analysis_results")
