"""Job Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobBase(BaseModel):
    """Base Job schema."""

    type: str
    payload: dict | None = None


class JobCreate(JobBase):
    """Schema for creating a new job."""

    pass


class JobUpdate(BaseModel):
    """Schema for updating a job."""

    status: str | None = None
    result: dict | None = None
    retry_count: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Job(JobBase):
    """Job schema for responses."""

    id: UUID
    status: str
    result: dict | None = None
    retry_count: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class JobMoveRequest(BaseModel):
    """Schema for move job request."""

    source_account_id: UUID
    source_item_id: str
    destination_account_id: UUID
    destination_folder_id: str = "root"


class JobUploadRequest(BaseModel):
    """Schema for upload job request (internal payload)."""

    account_id: UUID
    folder_id: str = "root"
    filename: str
    temp_path: str
