"""Metadata schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(from_attributes=True)


# --- Category Schemas ---
class MetadataCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class MetadataCategoryCreate(MetadataCategoryBase):
    pass


class MetadataCategory(MetadataCategoryBase):
    id: UUID
    created_at: datetime
    attributes: list[MetadataAttribute] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# --- Item Metadata Schemas ---
class ItemMetadataBase(BaseModel):
    item_id: str
    category_id: UUID
    values: dict = Field(default_factory=dict)


class ItemMetadataCreate(ItemMetadataBase):
    account_id: UUID

class ItemMetadataUpdate(BaseModel):
    values: dict


class ItemMetadata(ItemMetadataBase):
    id: UUID
    account_id: UUID
    version: int = 1
    updated_at: datetime
    category_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ItemMetadataHistory(BaseModel):
    id: UUID
    account_id: UUID
    item_id: str
    action: str
    previous_category_id: UUID | None = None
    previous_values: dict | None = None
    previous_version: int | None = None
    new_category_id: UUID | None = None
    new_values: dict | None = None
    new_version: int | None = None
    batch_id: UUID | None = None
    job_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MetadataRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    account_id: UUID | None = None
    is_active: bool = True
    priority: int = 100
    path_contains: str | None = None
    path_prefix: str | None = None
    target_category_id: UUID
    target_values: dict = Field(default_factory=dict)
    include_folders: bool = False


class MetadataRuleCreate(MetadataRuleBase):
    pass


class MetadataRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    account_id: UUID | None = None
    is_active: bool | None = None
    priority: int | None = None
    path_contains: str | None = None
    path_prefix: str | None = None
    target_category_id: UUID | None = None
    target_values: dict | None = None
    include_folders: bool | None = None


class MetadataRule(MetadataRuleBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MetadataRulePreviewRequest(BaseModel):
    account_id: UUID | None = None
    path_contains: str | None = None
    path_prefix: str | None = None
    include_folders: bool = False
    target_category_id: UUID
    target_values: dict = Field(default_factory=dict)
    limit: int = 50


class MetadataRulePreviewResponse(BaseModel):
    total_matches: int
    to_change: int
    already_compliant: int
    sample_item_ids: list[str]
