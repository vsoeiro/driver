"""add ai chat tables

Revision ID: 5a1c0ee9d2ab
Revises: 6f4d2c8b9a10
Create Date: 2026-02-25 20:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5a1c0ee9d2ab"
down_revision: Union[str, Sequence[str], None] = "6f4d2c8b9a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_chat_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_chat_sessions_user_updated_at",
        "ai_chat_sessions",
        ["user_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "ai_chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content_redacted", sa.Text(), nullable=False),
        sa.Column("raw_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["ai_chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_chat_messages_session_created_at",
        "ai_chat_messages",
        ["session_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ai_tool_calls",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False),
        sa.Column("input_redacted", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["ai_chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["ai_chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_tool_calls_session_created_at",
        "ai_tool_calls",
        ["session_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ai_pending_confirmations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False),
        sa.Column("input_redacted", sa.JSON(), nullable=False),
        sa.Column("action_payload", sa.JSON(), nullable=False),
        sa.Column("impact_summary", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["ai_chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_pending_confirmations_session_status",
        "ai_pending_confirmations",
        ["session_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_pending_confirmations_session_status", table_name="ai_pending_confirmations")
    op.drop_table("ai_pending_confirmations")

    op.drop_index("ix_ai_tool_calls_session_created_at", table_name="ai_tool_calls")
    op.drop_table("ai_tool_calls")

    op.drop_index("ix_ai_chat_messages_session_created_at", table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")

    op.drop_index("ix_ai_chat_sessions_user_updated_at", table_name="ai_chat_sessions")
    op.drop_table("ai_chat_sessions")
