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
    Integer,
    Boolean,
    ForeignKey,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class AppSetting(Base):
    """Application-level persisted settings."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


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

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_account_id",
            name="uq_linked_accounts_provider_provider_account_id",
        ),
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
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    dead_letter_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("account_id", "item_id", name="uq_item_metadata_account_item"),
    )


class ItemMetadataHistory(Base):
    """History of metadata changes per item."""

    __tablename__ = "item_metadata_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    metadata_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("item_metadata.id", ondelete="SET NULL"),
        nullable=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # CREATE, UPDATE, DELETE, UNDO
    previous_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    previous_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    previous_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class MetadataRule(Base):
    """Automatic metadata rule."""

    __tablename__ = "metadata_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("linked_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    path_contains: Mapped[str | None] = mapped_column(String(500), nullable=True)
    path_prefix: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    target_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metadata_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_values: Mapped[dict] = mapped_column(JSON, default={})
    include_folders: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
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



