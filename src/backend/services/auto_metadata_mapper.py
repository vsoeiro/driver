"""Automatic metadata mapping job dispatch based on file extension."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.jobs.commands import enqueue_job_command
from backend.services.metadata_libraries.service import MetadataLibraryService

logger = logging.getLogger(__name__)

COMIC_EXTENSIONS = {
    "cbz",
    "zip",
    "cbw",
    "pdf",
    "epub",
    "cbr",
    "rar",
    "cb7",
    "7z",
    "cbt",
    "tar",
}
BOOK_EXTENSIONS = {"pdf", "epub"}
IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "gif",
    "bmp",
    "tiff",
    "tif",
    "heic",
    "avif",
}
# Ambiguous extensions are resolved as BOOKS to keep deterministic routing.
COMIC_ONLY_EXTENSIONS = COMIC_EXTENSIONS - BOOK_EXTENSIONS


@dataclass(slots=True)
class AutoMapCandidate:
    item_id: str
    name: str | None = None
    extension: str | None = None
    item_type: str = "file"


def _normalize_extension(*, extension: str | None, name: str | None) -> str:
    ext = (extension or "").strip().lower().lstrip(".")
    if ext:
        return ext
    raw_name = str(name or "").strip()
    if "." not in raw_name:
        return ""
    return raw_name.rsplit(".", 1)[-1].strip().lower()


async def enqueue_auto_mapping_jobs(
    session: AsyncSession,
    *,
    account_id: UUID,
    candidates: Iterable[AutoMapCandidate],
    source: str,
    chunk_size: int = 500,
) -> dict[str, object]:
    """Enqueue metadata mapping jobs by extension for active libraries."""
    safe_chunk_size = max(1, min(5000, int(chunk_size)))
    by_type: dict[str, list[str]] = {
        "extract_comic_assets": [],
        "extract_book_assets": [],
        "analyze_image_assets": [],
    }

    for candidate in candidates:
        if (candidate.item_type or "file").lower() != "file":
            continue
        ext = _normalize_extension(extension=candidate.extension, name=candidate.name)
        if not ext:
            continue
        if ext in IMAGE_EXTENSIONS:
            by_type["analyze_image_assets"].append(str(candidate.item_id))
        elif ext in BOOK_EXTENSIONS:
            by_type["extract_book_assets"].append(str(candidate.item_id))
        elif ext in COMIC_ONLY_EXTENSIONS:
            by_type["extract_comic_assets"].append(str(candidate.item_id))

    library_service = MetadataLibraryService(session)
    active_types: set[str] = set()
    if await library_service.get_active_comics_category():
        active_types.add("extract_comic_assets")
    if await library_service.get_active_books_category():
        active_types.add("extract_book_assets")
    if await library_service.get_active_images_category():
        active_types.add("analyze_image_assets")

    total_jobs = 0
    job_ids: list[str] = []
    items_by_type: dict[str, int] = {}

    for job_type, item_ids in by_type.items():
        if not item_ids:
            continue
        if job_type not in active_types:
            continue
        items_by_type[job_type] = len(item_ids)
        for i in range(0, len(item_ids), safe_chunk_size):
            chunk = item_ids[i : i + safe_chunk_size]
            payload: dict[str, object] = {
                "account_id": str(account_id),
                "item_ids": chunk,
                "use_indexed_items": True,
            }
            if job_type == "analyze_image_assets":
                payload["reprocess"] = False
            job = await enqueue_job_command(
                session,
                job_type=job_type,
                payload=payload,
                dedupe_key=f"auto-map:{source}:{account_id}:{job_type}:{i}",
            )
            total_jobs += 1
            job_ids.append(str(job.id))

    if total_jobs:
        logger.info(
            "Auto metadata mapping jobs created account_id=%s source=%s total_jobs=%s items_by_type=%s",
            account_id,
            source,
            total_jobs,
            items_by_type,
        )

    return {
        "total_jobs": total_jobs,
        "job_ids": job_ids,
        "items_by_type": items_by_type,
    }

