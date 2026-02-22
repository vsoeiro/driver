"""add_job_queue_and_dedupe_fields

Revision ID: 2d84c79ab8d3
Revises: 1c3e9f7a5b20
Create Date: 2026-02-22 16:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2d84c79ab8d3"
down_revision: Union[str, Sequence[str], None] = "1c3e9f7a5b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTIVE_DEDUPE_WHERE_SQL = "dedupe_key IS NOT NULL AND status IN ('PENDING','RUNNING','RETRY_SCHEDULED')"


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _column_exists(inspector, "jobs", "queue_name"):
        op.add_column(
            "jobs",
            sa.Column(
                "queue_name",
                sa.String(length=120),
                nullable=False,
                server_default="driver:jobs",
            ),
        )
    if not _column_exists(inspector, "jobs", "dedupe_key"):
        op.add_column("jobs", sa.Column("dedupe_key", sa.String(length=255), nullable=True))

    op.execute("UPDATE jobs SET queue_name = 'driver:jobs' WHERE queue_name IS NULL OR trim(queue_name) = ''")

    inspector = sa.inspect(op.get_bind())
    if not _index_exists(inspector, "jobs", "ix_jobs_queue_name_status_created_at"):
        op.create_index(
            "ix_jobs_queue_name_status_created_at",
            "jobs",
            ["queue_name", "status", "created_at"],
            unique=False,
        )

    inspector = sa.inspect(op.get_bind())
    if not _index_exists(inspector, "jobs", "ux_jobs_active_dedupe_key"):
        dialect = bind.dialect.name
        where_expr = sa.text(ACTIVE_DEDUPE_WHERE_SQL)
        if dialect == "postgresql":
            op.create_index(
                "ux_jobs_active_dedupe_key",
                "jobs",
                ["dedupe_key"],
                unique=True,
                postgresql_where=where_expr,
            )
        elif dialect == "sqlite":
            op.create_index(
                "ux_jobs_active_dedupe_key",
                "jobs",
                ["dedupe_key"],
                unique=True,
                sqlite_where=where_expr,
            )
        else:
            op.create_index("ix_jobs_dedupe_key", "jobs", ["dedupe_key"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _index_exists(inspector, "jobs", "ix_jobs_dedupe_key"):
        op.drop_index("ix_jobs_dedupe_key", table_name="jobs")

    inspector = sa.inspect(op.get_bind())
    if _index_exists(inspector, "jobs", "ux_jobs_active_dedupe_key"):
        op.drop_index("ux_jobs_active_dedupe_key", table_name="jobs")

    inspector = sa.inspect(op.get_bind())
    if _index_exists(inspector, "jobs", "ix_jobs_queue_name_status_created_at"):
        op.drop_index("ix_jobs_queue_name_status_created_at", table_name="jobs")

    inspector = sa.inspect(op.get_bind())
    if _column_exists(inspector, "jobs", "dedupe_key"):
        op.drop_column("jobs", "dedupe_key")

    inspector = sa.inspect(op.get_bind())
    if _column_exists(inspector, "jobs", "queue_name"):
        op.drop_column("jobs", "queue_name")
