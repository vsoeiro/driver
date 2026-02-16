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


@register_handler("reindex_comic_covers")
async def reindex_comic_covers_handler(payload: dict, session: AsyncSession) -> dict:
    if payload.get("plugin_key", "comicrack_core") != "comicrack_core":
        raise ValueError("Unsupported plugin key for cover reindex")

    progress = JobProgressReporter.from_payload(session, payload)
    await progress.set_total(1)

    service = ComicMetadataService(session)
    stats = await service.reindex_mapped_comics(job_id=progress.job_id)
    await session.commit()

    await progress.update_metrics(
        mapped=stats.get("mapped", 0),
        skipped=stats.get("skipped", 0),
        failed=stats.get("failed", 0),
        accounts=stats.get("accounts", 0),
    )
    await progress.set_total(max(1, stats.get("total", 0)))
    progress.current = max(1, stats.get("total", 0))
    await progress.flush()

    return stats
