from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIChatSessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class AIChatSessionResponse(BaseModel):
    id: UUID
    user_id: str
    title: str
    title_pending: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIChatMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content_redacted: str
    raw_ref: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIChatMessageCreateRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


class AIToolTraceItem(BaseModel):
    id: UUID
    tool_name: str
    permission: str
    input_redacted: dict[str, Any] = Field(default_factory=dict)
    status: str
    duration_ms: int | None = None
    result_summary: dict[str, Any] | None = None
    error_summary: str | None = None
    created_at: datetime


class AIPendingConfirmationResponse(BaseModel):
    id: UUID
    tool_name: str
    permission: str
    input_redacted: dict[str, Any] = Field(default_factory=dict)
    impact_summary: dict[str, Any] | None = None
    status: str
    expires_at: datetime


class AIChatMessagePostResponse(BaseModel):
    assistant_message: AIChatMessageResponse
    tool_trace: list[AIToolTraceItem] = Field(default_factory=list)
    pending_confirmation: AIPendingConfirmationResponse | None = None


class AIConfirmationRequest(BaseModel):
    approve: bool


class AIConfirmationResponse(BaseModel):
    assistant_message: AIChatMessageResponse
    tool_trace: list[AIToolTraceItem] = Field(default_factory=list)
    pending_confirmation: AIPendingConfirmationResponse | None = None


class AIToolCatalogEntry(BaseModel):
    name: str
    permission: str
    description: str
    input_schema: dict[str, Any]


class AIToolCatalogResponse(BaseModel):
    tools: list[AIToolCatalogEntry] = Field(default_factory=list)
