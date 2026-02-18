"""Schemas for AI-assisted metadata workflows."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AISuggestAttribute(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    data_type: str = Field(..., pattern="^(text|number|date|boolean|select)$")
    is_required: bool = False
    options: dict | None = None

    @field_validator("options", mode="before")
    @classmethod
    def normalize_options(cls, value: Any) -> dict | None:
        if value is None:
            return None

        def normalize_option_values(raw_options: Any) -> list[str]:
            if not isinstance(raw_options, list):
                return []

            normalized: list[str] = []
            for option in raw_options:
                if isinstance(option, str):
                    candidate = option.strip()
                elif isinstance(option, dict):
                    candidate = str(option.get("value") or option.get("label") or "").strip()
                else:
                    candidate = str(option).strip()

                if candidate and candidate not in normalized:
                    normalized.append(candidate)
            return normalized

        if isinstance(value, list):
            normalized = normalize_option_values(value)
            return {"options": normalized} if normalized else None
        if isinstance(value, dict):
            if "options" in value:
                normalized = normalize_option_values(value.get("options"))
                return {"options": normalized} if normalized else None
            return value
        return None


class AICategorySuggestion(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    attributes: list[AISuggestAttribute] = Field(default_factory=list)


class AISuggestCategoryRequest(BaseModel):
    document_type: str = Field(..., min_length=1, max_length=120)
    sample_text: str | None = None
    create_in_db: bool = False


class AISuggestCategoryResponse(BaseModel):
    suggestion: AICategorySuggestion
    created_category_id: UUID | None = None
    created_attribute_ids: list[UUID] = Field(default_factory=list)


class AIExtractMetadataRequest(BaseModel):
    category_id: UUID
    document_text: str = Field(..., min_length=1)
    account_id: UUID | None = None
    item_id: str | None = None
    apply_to_item: bool = False

    @model_validator(mode="after")
    def validate_apply_fields(self) -> "AIExtractMetadataRequest":
        if self.apply_to_item:
            if self.account_id is None:
                raise ValueError("account_id is required when apply_to_item=true")
            if not self.item_id:
                raise ValueError("item_id is required when apply_to_item=true")
        return self


class AIExtractMetadataResponse(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    notes: str | None = None
    applied: bool = False
    metadata_id: UUID | None = None


class AIHealthResponse(BaseModel):
    enabled: bool
    provider: str
    model: str
    available: bool
    detail: str | None = None


class AIComicSuggestRequest(BaseModel):
    category_id: UUID
    title: str = Field(..., min_length=1)
    account_id: UUID
    item_id: str = Field(..., min_length=1)
    cover_account_id: UUID | None = None
    cover_item_id: str | None = None


class AIComicSuggestResponse(BaseModel):
    category_id: UUID
    account_id: UUID
    item_id: str
    suggestions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    notes: str | None = None
    model: str
