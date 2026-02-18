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
    managed_by_plugin: bool = False
    plugin_key: str | None = None
    plugin_field_key: str | None = None
    is_locked: bool = False

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
    is_active: bool = True
    managed_by_plugin: bool = False
    plugin_key: str | None = None
    is_locked: bool = False
    attributes: list[MetadataAttribute] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MetadataPlugin(BaseModel):
    key: str
    name: str
    description: str | None = None
    is_active: bool
    category_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Item Metadata Schemas ---
class ItemMetadataBase(BaseModel):
    item_id: str
    category_id: UUID
    values: dict = Field(default_factory=dict)
    ai_suggestions: dict = Field(default_factory=dict)


class ItemMetadataCreate(ItemMetadataBase):
    account_id: UUID

class ItemMetadataUpdate(BaseModel):
    values: dict
    ai_suggestions: dict | None = None


class ItemMetadata(ItemMetadataBase):
    id: UUID
    account_id: UUID
    version: int = 1
    updated_at: datetime
    category_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AIPendingSuggestion(BaseModel):
    value: str | int | float | bool | None = None
    confidence: float | None = None
    source: str | None = None
    model: str | None = None
    generated_at: datetime | None = None
    notes: str | None = None


class ItemMetadataAISuggestionsUpdate(BaseModel):
    category_id: UUID
    suggestions: dict[str, AIPendingSuggestion] = Field(default_factory=dict)


class ItemMetadataAIFieldActionRequest(BaseModel):
    category_id: UUID
    attribute_id: str


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
    apply_metadata: bool = True
    apply_rename: bool = False
    rename_template: str | None = None
    apply_move: bool = False
    destination_account_id: UUID | None = None
    destination_folder_id: str = "root"
    destination_path_template: str | None = None
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
    apply_metadata: bool | None = None
    apply_rename: bool | None = None
    rename_template: str | None = None
    apply_move: bool | None = None
    destination_account_id: UUID | None = None
    destination_folder_id: str | None = None
    destination_path_template: str | None = None
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
    apply_metadata: bool = True
    apply_rename: bool = False
    rename_template: str | None = None
    apply_move: bool = False
    destination_account_id: UUID | None = None
    destination_folder_id: str = "root"
    destination_path_template: str | None = None
    limit: int = 50


class MetadataRulePreviewResponse(BaseModel):
    total_matches: int
    to_change: int
    already_compliant: int
    sample_item_ids: list[str]
