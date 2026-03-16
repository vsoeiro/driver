"""Job-related enums used across API, services, and workers."""

from __future__ import annotations

from enum import StrEnum


class JobType(StrEnum):
    SYNC_ITEMS = "sync_items"
    UPLOAD_FILE = "upload_file"
    MOVE_ITEMS = "move_items"
    EXTRACT_ZIP_CONTENTS = "extract_zip_contents"
    UPDATE_METADATA = "update_metadata"
    APPLY_METADATA_RECURSIVE = "apply_metadata_recursive"
    REMOVE_METADATA_RECURSIVE = "remove_metadata_recursive"
    UNDO_METADATA_BATCH = "undo_metadata_batch"
    APPLY_METADATA_RULE = "apply_metadata_rule"
    EXTRACT_COMIC_ASSETS = "extract_comic_assets"
    EXTRACT_BOOK_ASSETS = "extract_book_assets"
    EXTRACT_LIBRARY_COMIC_ASSETS = "extract_library_comic_assets"
    REINDEX_COMIC_COVERS = "reindex_comic_covers"
    ANALYZE_IMAGE_ASSETS = "analyze_image_assets"
    ANALYZE_LIBRARY_IMAGE_ASSETS = "analyze_library_image_assets"
    REMOVE_DUPLICATE_FILES = "remove_duplicate_files"
    AI_GENERATE_CHAT_TITLE = "ai_generate_chat_title"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


def normalize_job_type(value: str | JobType) -> str:
    """Normalize incoming type value into persisted snake_case string."""
    if isinstance(value, JobType):
        return value.value
    return str(value or "").strip().lower()
