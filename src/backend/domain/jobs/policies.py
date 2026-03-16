"""Centralized queue/retry/dedupe policies for job types."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from backend.domain.jobs.types import JobType, normalize_job_type

DEFAULT_JOB_QUEUE_ALIAS_BY_TYPE: dict[str, str] = {
    JobType.SYNC_ITEMS.value: "sync",
    JobType.UPLOAD_FILE.value: "io",
    JobType.MOVE_ITEMS.value: "io",
    JobType.EXTRACT_ZIP_CONTENTS.value: "io",
    JobType.UPDATE_METADATA.value: "metadata",
    JobType.APPLY_METADATA_RECURSIVE.value: "metadata",
    JobType.REMOVE_METADATA_RECURSIVE.value: "metadata",
    JobType.UNDO_METADATA_BATCH.value: "metadata",
    JobType.APPLY_METADATA_RULE.value: "rules",
    JobType.EXTRACT_COMIC_ASSETS.value: "comics",
    JobType.EXTRACT_BOOK_ASSETS.value: "comics",
    JobType.EXTRACT_LIBRARY_COMIC_ASSETS.value: "comics",
    JobType.REINDEX_COMIC_COVERS.value: "comics",
    JobType.ANALYZE_IMAGE_ASSETS.value: "vision",
    JobType.ANALYZE_LIBRARY_IMAGE_ASSETS.value: "vision",
    JobType.REMOVE_DUPLICATE_FILES.value: "io",
}

DEFAULT_JOB_MAX_RETRIES_BY_TYPE: dict[str, int] = {
    JobType.SYNC_ITEMS.value: 2,
    JobType.UPLOAD_FILE.value: 4,
    JobType.MOVE_ITEMS.value: 3,
    JobType.EXTRACT_ZIP_CONTENTS.value: 1,
    JobType.UPDATE_METADATA.value: 2,
    JobType.APPLY_METADATA_RECURSIVE.value: 2,
    JobType.REMOVE_METADATA_RECURSIVE.value: 2,
    JobType.UNDO_METADATA_BATCH.value: 2,
    JobType.APPLY_METADATA_RULE.value: 2,
    JobType.EXTRACT_COMIC_ASSETS.value: 1,
    JobType.EXTRACT_BOOK_ASSETS.value: 1,
    JobType.EXTRACT_LIBRARY_COMIC_ASSETS.value: 1,
    JobType.REINDEX_COMIC_COVERS.value: 1,
    JobType.ANALYZE_IMAGE_ASSETS.value: 1,
    JobType.ANALYZE_LIBRARY_IMAGE_ASSETS.value: 1,
    JobType.REMOVE_DUPLICATE_FILES.value: 1,
}

DEFAULT_JOB_DEDUPE_KEYS_BY_TYPE: dict[str, tuple[str, ...]] = {
    JobType.SYNC_ITEMS.value: ("account_id",),
    JobType.EXTRACT_ZIP_CONTENTS.value: (
        "source_account_id",
        "source_item_id",
        "destination_account_id",
        "destination_folder_id",
        "delete_source_after_extract",
    ),
    JobType.UPDATE_METADATA.value: ("account_id", "root_item_id", "category_name"),
    JobType.APPLY_METADATA_RECURSIVE.value: ("account_id", "path_prefix", "category_id"),
    JobType.REMOVE_METADATA_RECURSIVE.value: ("account_id", "path_prefix"),
    JobType.UNDO_METADATA_BATCH.value: ("batch_id",),
    JobType.APPLY_METADATA_RULE.value: ("rule_id",),
    JobType.EXTRACT_COMIC_ASSETS.value: ("account_id", "item_ids", "use_indexed_items"),
    JobType.EXTRACT_BOOK_ASSETS.value: ("account_id", "item_ids", "use_indexed_items"),
    JobType.EXTRACT_LIBRARY_COMIC_ASSETS.value: ("account_ids", "chunk_size"),
    JobType.REINDEX_COMIC_COVERS.value: ("plugin_key", "library_key"),
    JobType.ANALYZE_IMAGE_ASSETS.value: ("account_id", "item_ids", "reprocess"),
    JobType.ANALYZE_LIBRARY_IMAGE_ASSETS.value: ("account_ids", "chunk_size", "reprocess"),
    JobType.REMOVE_DUPLICATE_FILES.value: (
        "preferred_account_id",
        "account_id",
        "scope",
        "extensions",
        "hide_low_priority",
    ),
}


def resolve_job_queue_alias(job_type: str, settings: Any, requested_queue_name: str | None) -> str | None:
    """Resolve alias/name (not full queue name) before queue adapter normalization."""
    if requested_queue_name is not None and str(requested_queue_name).strip():
        return str(requested_queue_name).strip()

    queue_map = dict(DEFAULT_JOB_QUEUE_ALIAS_BY_TYPE)
    queue_map.update(getattr(settings, "job_type_queue_map", {}) or {})
    return queue_map.get(job_type, "default")


def resolve_job_max_retries(job_type: str, settings: Any, requested_max_retries: int | None) -> int:
    """Resolve max retries from explicit request -> policy map -> default."""
    if requested_max_retries is not None:
        return max(0, int(requested_max_retries))
    retry_map = dict(DEFAULT_JOB_MAX_RETRIES_BY_TYPE)
    retry_map.update(getattr(settings, "job_type_max_retries_map", {}) or {})
    default_retries = max(0, int(getattr(settings, "job_default_max_retries", 3)))
    return max(0, int(retry_map.get(job_type, default_retries)))


def normalize_dedupe_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def build_default_dedupe_key(job_type: str | JobType, payload: dict[str, Any]) -> str | None:
    """Build deterministic dedupe key from per-type key fields."""
    normalized_type = normalize_job_type(job_type)
    dedupe_fields = DEFAULT_JOB_DEDUPE_KEYS_BY_TYPE.get(normalized_type)
    if not dedupe_fields:
        return None
    dedupe_payload = {field: payload.get(field) for field in dedupe_fields if field in payload}
    if not dedupe_payload:
        return None
    canonical_payload = json.dumps(
        dedupe_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    digest = sha256(canonical_payload.encode("utf-8")).hexdigest()
    return f"{normalized_type}:{digest}"


def resolve_job_dedupe_key(
    *,
    job_type: str | JobType,
    payload: dict[str, Any],
    requested_dedupe_key: str | None,
) -> str | None:
    explicit_key = normalize_dedupe_key(requested_dedupe_key)
    if explicit_key is not None:
        return explicit_key
    return build_default_dedupe_key(job_type, payload)
