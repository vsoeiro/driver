"""Job Pydantic schemas."""

from typing import Any, Literal
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobBase(BaseModel):
    """Base Job schema."""

    type: str
    payload: dict | None = None
    max_retries: int | None = None
    queue_name: str | None = None
    dedupe_key: str | None = None


class JobCreate(JobBase):
    """Schema for creating a new job."""

    pass


class JobUpdate(BaseModel):
    """Schema for updating a job."""

    status: str | None = None
    result: dict | None = None
    retry_count: int | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    progress_percent: int | None = None
    metrics: dict | None = None
    next_retry_at: datetime | None = None
    last_error: str | None = None
    dead_lettered_at: datetime | None = None
    dead_letter_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Job(JobBase):
    """Job schema for responses."""

    id: UUID
    status: str
    result: dict | None = None
    retry_count: int
    max_retries: int
    queue_name: str
    dedupe_key: str | None = None
    progress_current: int
    progress_total: int | None = None
    progress_percent: int
    metrics: dict | None = None
    next_retry_at: datetime | None = None
    last_error: str | None = None
    dead_lettered_at: datetime | None = None
    dead_letter_reason: str | None = None
    reprocessed_from_job_id: UUID | None = None
    queue_position: int | None = None
    estimated_wait_seconds: int | None = None
    estimated_duration_seconds: int | None = None
    estimated_start_at: datetime | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class JobAttempt(BaseModel):
    """Job execution attempt details."""

    id: UUID
    job_id: UUID
    attempt_number: int
    status: str
    triggered_by: str
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: int | None = None

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


class JobSyncRequest(BaseModel):
    """Schema for sync items job request."""
    account_id: UUID


class JobMetadataUpdateRequest(BaseModel):
    """Schema for bulk metadata update job request."""

    account_id: UUID
    root_item_id: str
    metadata: dict[str, Any]  # Key: Attribute Name, Value: Value
    category_name: str


class JobApplyMetadataRecursiveRequest(BaseModel):
    """Schema for recursive metadata application using local items table."""

    account_id: UUID
    path_prefix: str
    category_id: UUID
    values: dict[str, Any] = {}
    include_folders: bool = False


class JobRemoveMetadataRecursiveRequest(BaseModel):
    """Schema for recursive metadata removal using local items table."""

    account_id: UUID
    path_prefix: str


class JobUndoMetadataBatchRequest(BaseModel):
    """Schema for metadata batch undo job request."""

    batch_id: UUID


class JobApplyRuleRequest(BaseModel):
    """Schema for metadata rule apply job request."""

    rule_id: UUID


class JobExtractComicAssetsRequest(BaseModel):
    """Schema for comic asset extraction request."""

    account_id: UUID
    item_ids: list[str]


class JobExtractBookAssetsRequest(BaseModel):
    """Schema for book asset extraction request."""

    account_id: UUID
    item_ids: list[str]


class JobReindexComicCoversRequest(BaseModel):
    """Schema for metadata-library-driven comic cover reindex request."""

    library_key: str = Field(default="comics_core", alias="plugin_key")

    model_config = ConfigDict(populate_by_name=True)


class JobExtractLibraryComicAssetsRequest(BaseModel):
    """Schema for library-wide comic extraction (all CBR/CBZ already synced)."""

    account_ids: list[UUID] | None = None
    chunk_size: int = 1000


class JobExtractLibraryComicAssetsResponse(BaseModel):
    """Summary of chunked comic extraction jobs created from library index."""

    total_items: int
    total_jobs: int
    chunk_size: int
    job_ids: list[UUID]


class JobExtractLibraryBookAssetsRequest(BaseModel):
    """Schema for library-wide book extraction (all supported books already synced)."""

    account_ids: list[UUID] | None = None
    chunk_size: int = 500


class JobExtractLibraryBookAssetsResponse(BaseModel):
    """Summary of chunked book extraction jobs created from library index."""

    total_items: int
    total_jobs: int
    chunk_size: int
    job_ids: list[UUID]


class JobAnalyzeImageAssetsRequest(BaseModel):
    """Schema for image analysis request on selected item ids."""

    account_id: UUID
    item_ids: list[str]
    use_indexed_items: bool = True
    reprocess: bool = False


class JobAnalyzeLibraryImageAssetsRequest(BaseModel):
    """Schema for chunked image analysis over indexed files."""

    account_ids: list[UUID] | None = None
    chunk_size: int = 500
    reprocess: bool = False


class JobAnalyzeLibraryImageAssetsResponse(BaseModel):
    """Summary of chunked image analysis jobs."""

    total_items: int
    total_jobs: int
    chunk_size: int
    job_ids: list[UUID]


class JobMapLibraryBooksRequest(BaseModel):
    """Schema for chunked books metadata mapping over indexed files."""

    account_ids: list[UUID] | None = None
    chunk_size: int = 500


class JobMapLibraryBooksResponse(BaseModel):
    """Summary of chunked books mapping jobs."""

    total_items: int
    total_jobs: int
    chunk_size: int
    job_ids: list[UUID]


class JobRemoveDuplicateFilesRequest(BaseModel):
    """Schema for duplicate-removal job based on Similar Files filters."""

    preferred_account_id: UUID
    account_id: UUID | None = None
    scope: Literal["all", "same_account", "cross_account"] = "all"
    extensions: list[str] = []
    hide_low_priority: bool = False

