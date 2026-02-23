"""provider_scoped_unique_linked_accounts

Revision ID: 4f2e0f7861d4
Revises: ff93ad097510
Create Date: 2026-02-15 02:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f2e0f7861d4"
down_revision: Union[str, Sequence[str], None] = "ff93ad097510"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _recreate_linked_accounts_sqlite(composite_unique: bool) -> None:
    """Recreate linked_accounts table for SQLite with desired unique constraint."""
    op.execute("PRAGMA foreign_keys=OFF")

    if composite_unique:
        unique_args = [sa.UniqueConstraint("provider", "provider_account_id", name="uq_linked_accounts_provider_provider_account_id")]
    else:
        unique_args = [sa.UniqueConstraint("provider_account_id", name="uq_linked_accounts_provider_account_id")]

    op.create_table(
        "linked_accounts_tmp",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        *unique_args,
    )

    op.execute(
        """
        INSERT INTO linked_accounts_tmp (
            id, provider, provider_account_id, email, display_name,
            access_token_encrypted, refresh_token_encrypted, token_expires_at,
            is_active, created_at, updated_at
        )
        SELECT
            id, provider, provider_account_id, email, display_name,
            access_token_encrypted, refresh_token_encrypted, token_expires_at,
            is_active, created_at, updated_at
        FROM linked_accounts
        """
    )

    op.drop_table("linked_accounts")
    op.rename_table("linked_accounts_tmp", "linked_accounts")
    op.execute("PRAGMA foreign_keys=ON")


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _recreate_linked_accounts_sqlite(composite_unique=True)
        return

    inspector = sa.inspect(bind)
    uniques = inspector.get_unique_constraints("linked_accounts")

    with op.batch_alter_table("linked_accounts") as batch_op:
        for constraint in uniques:
            cols = constraint.get("column_names") or []
            name = constraint.get("name")
            if cols == ["provider_account_id"] and name:
                batch_op.drop_constraint(name, type_="unique")

        batch_op.create_unique_constraint(
            "uq_linked_accounts_provider_provider_account_id",
            ["provider", "provider_account_id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _recreate_linked_accounts_sqlite(composite_unique=False)
        return

    with op.batch_alter_table("linked_accounts") as batch_op:
        batch_op.drop_constraint("uq_linked_accounts_provider_provider_account_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_linked_accounts_provider_account_id",
            ["provider_account_id"],
        )
