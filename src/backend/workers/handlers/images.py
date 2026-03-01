"""Image analysis job handlers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.error_items import ErrorItemsCollector
from backend.db.models import Item
from backend.services.image_analysis.service import ImageAnalysisService, IndexedImageItem
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter

IMAGE_ERROR_ITEMS_LIMIT = 50
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff", "tif", "heic", "avif"}


@register_handler("analyze_image_assets")
async def analyze_image_assets_handler(payload: dict, session: AsyncSession) -> dict:
    account_id = UUID(payload["account_id"])
    item_ids = [str(item_id) for item_id in payload.get("item_ids", [])]
    if not item_ids:
        return {
            "total": 0,
            "processed": 0,
            "mapped": 0,
            "skipped": 0,
            "failed": 0,
            "error_items": [],
            "error_items_truncated": 0,
        }

    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    await progress.set_total(len(item_ids))

    service = ImageAnalysisService(session)
    if payload.get("use_indexed_items"):
        stmt = select(Item.item_id, Item.name, Item.extension, Item.item_type, Item.size).where(
            Item.account_id == account_id,
            Item.item_id.in_(item_ids),
            Item.item_type == "file",
        )
        rows = (await session.execute(stmt)).all()
        indexed = [
            IndexedImageItem(
                id=str(item_id),
                name=str(name or item_id),
                extension=str(extension).lower() if extension else None,
                item_type=str(item_type or "file"),
                size=int(size) if size is not None else None,
            )
            for item_id, name, extension, item_type, size in rows
        ]
        stats = await service.process_indexed_items(
            account_id,
            indexed,
            job_id=progress.job_id,
            progress_reporter=progress,
            initialize_progress_total=False,
            reprocess=bool(payload.get("reprocess")),
        )
    else:
        stats = await service.process_item_ids(
            account_id,
            item_ids,
            job_id=progress.job_id,
            progress_reporter=progress,
            reprocess=bool(payload.get("reprocess")),
        )

    await progress.update_metrics(
        processed=stats["processed"],
        mapped=stats["mapped"],
        skipped=stats["skipped"],
        failed=stats["failed"],
        error_items=stats.get("error_items", []),
        error_items_truncated=stats.get("error_items_truncated", 0),
    )
    await progress.set_total(stats["total"])
    progress.current = stats["total"]
    await progress.flush()

    return stats


@register_handler("analyze_library_image_assets")
async def analyze_library_image_assets_handler(payload: dict, session: AsyncSession) -> dict:
    account_ids = payload.get("account_ids") or []
    normalized_account_ids = []
    for raw_id in account_ids:
        try:
            normalized_account_ids.append(UUID(str(raw_id)))
        except ValueError:
            continue

    stmt = select(Item.account_id, Item.item_id, Item.name, Item.extension, Item.size).where(
        Item.item_type == "file",
        func.lower(func.coalesce(Item.extension, "")).in_(tuple(IMAGE_EXTENSIONS)),
    )
    if normalized_account_ids:
        stmt = stmt.where(Item.account_id.in_(normalized_account_ids))

    result = await session.execute(stmt)
    rows = result.all()
    if not rows:
        return {
            "total": 0,
            "processed": 0,
            "mapped": 0,
            "skipped": 0,
            "failed": 0,
            "accounts": 0,
            "error_items": [],
            "error_items_truncated": 0,
        }

    by_account: dict[UUID, list[IndexedImageItem]] = {}
    for account_id, item_id, name, extension, size in rows:
        by_account.setdefault(account_id, []).append(
            IndexedImageItem(
                id=str(item_id),
                name=str(name or item_id),
                extension=str(extension).lower() if extension else None,
                item_type="file",
                size=int(size) if size is not None else None,
            )
        )

    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    await progress.set_total(len(rows))

    service = ImageAnalysisService(session)
    stats = {
        "total": len(rows),
        "processed": 0,
        "mapped": 0,
        "skipped": 0,
        "failed": 0,
        "accounts": len(by_account),
        "error_items": [],
        "error_items_truncated": 0,
    }
    error_collector = ErrorItemsCollector(stats, limit=IMAGE_ERROR_ITEMS_LIMIT)
    for account_id, indexed_items in by_account.items():
        account_stats = await service.process_indexed_items(
            account_id,
            indexed_items,
            job_id=progress.job_id,
            progress_reporter=progress,
            initialize_progress_total=False,
            reprocess=bool(payload.get("reprocess")),
        )
        stats["processed"] += account_stats.get("processed", 0)
        stats["mapped"] += account_stats.get("mapped", 0)
        stats["skipped"] += account_stats.get("skipped", 0)
        stats["failed"] += account_stats.get("failed", 0)
        error_collector.merge(account_stats)

    await progress.update_metrics(
        processed=stats["processed"],
        mapped=stats["mapped"],
        skipped=stats["skipped"],
        failed=stats["failed"],
        accounts=stats["accounts"],
        error_items=stats.get("error_items", []),
        error_items_truncated=stats.get("error_items_truncated", 0),
    )
    progress.current = stats["total"]
    await progress.flush(force=True)
    return stats
