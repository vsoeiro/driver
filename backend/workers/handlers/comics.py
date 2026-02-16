"""Comic extraction job handler."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.comics import ComicMetadataService
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter


@register_handler("extract_comic_assets")
async def extract_comic_assets_handler(payload: dict, session: AsyncSession) -> dict:
    account_id = UUID(payload["account_id"])
    item_ids = [str(item_id) for item_id in payload.get("item_ids", [])]
    if not item_ids:
        return {"total": 0, "mapped": 0, "skipped": 0, "failed": 0}

    progress = JobProgressReporter.from_payload(session, payload)
    await progress.set_total(len(item_ids))

    service = ComicMetadataService(session)
    stats = await service.process_item_ids(
        account_id,
        item_ids,
        job_id=progress.job_id,
    )
    await session.commit()

    await progress.update_metrics(
        mapped=stats["mapped"],
        skipped=stats["skipped"],
        failed=stats["failed"],
    )
    await progress.set_total(stats["total"])
    progress.current = stats["total"]
    await progress.flush()

    return stats
