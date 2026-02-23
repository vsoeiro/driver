"""add_job_attempts_and_reprocess_reference

Revision ID: b8f1d2a3c4e5
Revises: a3d9f1c7b2e4
Create Date: 2026-02-17 10:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8f1d2a3c4e5"
down_revision: Union[str, Sequence[str], None] = "a3d9f1c7b2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("reprocessed_from_job_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_reprocessed_from_job_id",
        "jobs",
        "jobs",
        ["reprocessed_from_job_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "job_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("triggered_by", sa.String(length=30), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_attempts_job_id", "job_attempts", ["job_id"], unique=False)
    op.create_index("ix_job_attempts_status", "job_attempts", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_attempts_status", table_name="job_attempts")
    op.drop_index("ix_job_attempts_job_id", table_name="job_attempts")
    op.drop_table("job_attempts")

    op.drop_constraint("fk_jobs_reprocessed_from_job_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "reprocessed_from_job_id")
