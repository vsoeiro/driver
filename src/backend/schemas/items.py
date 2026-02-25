from uuid import UUID

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.drive import DriveItemBase
from backend.schemas.metadata import ItemMetadata


class ItemResponse(DriveItemBase):
    """Item response model.
    
    Includes metadata and account information.
    """
    account_id: UUID
    item_id: str
    parent_id: str | None = None
    path: str | None = None
    item_type: str
    mime_type: str | None = None
    extension: str | None = None
    
    metadata: ItemMetadata | None = None
    
    class Config:
        from_attributes = True


class ItemListResponse(BaseModel):
    """Response for listing items."""
    items: list[ItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class BatchMetadataUpdate(BaseModel):
    """Request to update metadata for multiple items."""
    item_ids: list[str]
    account_id: UUID
    category_id: UUID
    values: dict


class SimilarItemEntry(BaseModel):
    """Single item inside a similarity group."""

    account_id: UUID
    item_id: str
    name: str
    path: str | None = None
    extension: str | None = None
    size: int
    modified_at: datetime | None = None
    source_records: int = 1


class SimilarItemsGroup(BaseModel):
    """Group of potentially duplicated files."""

    match_type: Literal["with_extension", "without_extension"]
    name: str
    size: int
    extension: str | None = None
    extensions: list[str] = Field(default_factory=list)
    total_items: int
    total_accounts: int
    has_same_account_matches: bool
    has_cross_account_matches: bool
    deletable_items: int = 0
    potential_savings_bytes: int = 0
    priority_level: Literal["normal", "low"] = "normal"
    low_priority_reasons: list[str] = Field(default_factory=list)
    items: list[SimilarItemEntry] = Field(default_factory=list)


class SimilarItemsReportResponse(BaseModel):
    """Paginated report with possible similar files."""

    generated_at: datetime
    total_groups: int
    total_items: int
    collapsed_records: int = 0
    potential_savings_bytes: int = 0
    page: int
    page_size: int
    total_pages: int
    groups: list[SimilarItemsGroup] = Field(default_factory=list)
