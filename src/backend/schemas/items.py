from uuid import UUID

from pydantic import BaseModel

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
