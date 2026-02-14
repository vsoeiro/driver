"""SQLAlchemy database models.

This module defines the database models for users and linked Microsoft accounts.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    String,
    Text,
    JSON,
    ForeignKey,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class LinkedAccount(Base):
    """Linked Microsoft account model.

    Stores OAuth tokens and account information for a connected
    Microsoft account.

    Attributes
    ----------
    id : UUID
        Primary key.
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
    """

    __tablename__ = "linked_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
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


class Job(Base):
    """Background job model.

    Stores information about background jobs, their status, and execution results.

    Attributes
    ----------
    id : UUID
        Primary key.
    type : str
        Type of job (e.g., 'move_items').
    status : str
        Current status of the job (PENDING, RUNNING, COMPLETED, FAILED).
    payload : dict
        JSON payload containing job arguments.
    result : dict
        JSON result or error information.
    retry_count : int
        Number of times the job has been retried.
    created_at : datetime
        Job creation timestamp.
    started_at : datetime
        Job start timestamp.
    completed_at : datetime
        Job completion timestamp.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    payload: Mapped[dict] = mapped_column(JSON, nullable=True)  # Stored as JSON string
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Stored as JSON string
    retry_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class MetadataCategory(Base):
    """Metadata category model.

    Represents a group of attributes, e.g., 'Contract', 'Invoice'.
    """
    __tablename__ = "metadata_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    attributes: Mapped[list["MetadataAttribute"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class MetadataAttribute(Base):
    """Metadata attribute model.

    Represents a specific field within a category, e.g., 'Contract Number'.
    """
    __tablename__ = "metadata_attributes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metadata_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)  # text, number, date, boolean, select
    options: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # For 'select' type: {"options": ["A", "B"]}
    is_required: Mapped[bool] = mapped_column(default=False)

    category: Mapped["MetadataCategory"] = relationship(back_populates="attributes")


class ItemMetadata(Base):
    """Item metadata model.

    Stores the assigned category and attribute values for a specific file/folder.
    """
    __tablename__ = "item_metadata"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    item_id: Mapped[str] = mapped_column(String(255), nullable=False)  # OneDrive Item ID
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    values: Mapped[dict] = mapped_column(JSON, default={})  # Key: Attribute ID, Value: User Input
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class Item(Base):
    """File system item model.

    Stores static properties of files and folders to avoid repeated Graph API calls
    and to enable SQL-based filtering/sorting.
    """
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("linked_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[str] = mapped_column(String(255), nullable=False)  # OneDrive Item ID
    parent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # Full path /Folder/File.ext
    
    item_type: Mapped[str] = mapped_column(String(50), default="file")  # file, folder
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extension: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint('account_id', 'item_id', name='uq_items_account_item'),
    )






