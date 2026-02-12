"""SQLAlchemy database models.

This module defines the database models for users and linked Microsoft accounts.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class User(Base):
    """User model representing an application user.

    A user can have multiple linked Microsoft accounts.

    Attributes
    ----------
    id : UUID
        Primary key.
    email : str
        User email address, unique.
    name : str
        User display name.
    created_at : datetime
        Account creation timestamp.
    updated_at : datetime
        Last update timestamp.
    linked_accounts : list[LinkedAccount]
        Related Microsoft accounts.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    linked_accounts: Mapped[list["LinkedAccount"]] = relationship(
        "LinkedAccount",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class LinkedAccount(Base):
    """Linked Microsoft account model.

    Stores OAuth tokens and account information for a connected
    Microsoft account.

    Attributes
    ----------
    id : UUID
        Primary key.
    user_id : UUID
        Foreign key to the parent user.
    provider : str
        OAuth provider name (e.g., 'microsoft').
    provider_account_id : str
        Unique account ID from the provider.
    email : str
        Account email address.
    display_name : str
        Account display name.
    access_token_encrypted : str
        Encrypted OAuth access token.
    refresh_token_encrypted : str
        Encrypted OAuth refresh token.
    token_expires_at : datetime
        Access token expiration timestamp.
    is_active : bool
        Whether the account is currently active.
    created_at : datetime
        Account link creation timestamp.
    updated_at : datetime
        Last update timestamp.
    user : User
        Parent user relationship.
    """

    __tablename__ = "linked_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="microsoft")
    provider_account_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user: Mapped["User"] = relationship("User", back_populates="linked_accounts")





