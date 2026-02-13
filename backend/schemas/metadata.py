"""Metadata schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Attribute Schemas ---
class MetadataAttributeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    data_type: str = Field(..., pattern="^(text|number|date|boolean|select)$")
    options: dict | None = None
    is_required: bool = False


class MetadataAttributeCreate(MetadataAttributeBase):
    pass


class MetadataAttributeUpdate(BaseModel):
    name: str | None = None
    data_type: str | None = None
    options: dict | None = None
    is_required: bool | None = None


class MetadataAttribute(MetadataAttributeBase):
    id: UUID
    category_id: UUID

    class Config:
        from_attributes = True


# --- Category Schemas ---
class MetadataCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class MetadataCategoryCreate(MetadataCategoryBase):
    pass


class MetadataCategory(MetadataCategoryBase):
    id: UUID
    created_at: datetime
    attributes: list[MetadataAttribute] = []

    class Config:
        from_attributes = True


# --- Item Metadata Schemas ---
class ItemMetadataBase(BaseModel):
    item_id: str
    category_id: UUID
    values: dict = {}


class ItemMetadataCreate(ItemMetadataBase):
    account_id: UUID

class ItemMetadataUpdate(BaseModel):
    values: dict


class ItemMetadata(ItemMetadataBase):
    id: UUID
    account_id: UUID
    updated_at: datetime

    class Config:
        from_attributes = True
