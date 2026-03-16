"""ZIP extraction job handler."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.drive.zip_extraction_service import ZipExtractionService
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter


@register_handler("extract_zip_contents")
async def extract_zip_contents_handler(payload: dict, session: AsyncSession) -> dict:
    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    service = ZipExtractionService(session)
    stats = await service.extract_zip(
        source_account_id=UUID(str(payload["source_account_id"])),
        source_item_id=str(payload["source_item_id"]),
        destination_account_id=UUID(str(payload["destination_account_id"])),
        destination_folder_id=str(payload.get("destination_folder_id") or "root"),
        delete_source_after_extract=bool(payload.get("delete_source_after_extract")),
        progress_reporter=progress,
    )
    await session.commit()
    if progress.total is None:
        await progress.set_total(int(stats.get("total", 0) or 0))
    progress.current = int(stats.get("total", 0) or 0)
    await progress.update_metrics(
        total=int(stats.get("total", 0) or 0),
        success=int(stats.get("success", 0) or 0),
        failed=int(stats.get("failed", 0) or 0),
        skipped=int(stats.get("skipped", 0) or 0),
        created_folders=int(stats.get("created_folders", 0) or 0),
        wrapper_folder_id=stats.get("wrapper_folder_id"),
        wrapper_folder_name=stats.get("wrapper_folder_name"),
        deleted_source=bool(stats.get("deleted_source")),
        auto_jobs_created=int(stats.get("auto_jobs_created", 0) or 0),
        auto_job_ids=list(stats.get("auto_job_ids") or []),
        error_items=list(stats.get("error_items") or []),
        error_items_truncated=int(stats.get("error_items_truncated", 0) or 0),
    )
    await progress.flush(force=True)
    return stats
