"""Book extraction job handlers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Item
from backend.services.metadata_libraries.books.metadata_service import (
    BookMetadataService,
    IndexedBookItem,
)
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter


@register_handler("extract_book_assets")
async def extract_book_assets_handler(payload: dict, session: AsyncSession) -> dict:
    account_id = UUID(payload["account_id"])
    item_ids = [str(item_id) for item_id in payload.get("item_ids", [])]
    if not item_ids:
        return {"total": 0, "mapped": 0, "skipped": 0, "failed": 0}

    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    await progress.set_total(len(item_ids))

    service = BookMetadataService(session)
    if payload.get("use_indexed_items"):
        stmt = select(Item.item_id, Item.name, Item.extension, Item.item_type, Item.size).where(
            Item.account_id == account_id,
            Item.item_id.in_(item_ids),
            Item.item_type == "file",
        )
        rows = (await session.execute(stmt)).all()
        indexed = [
            IndexedBookItem(
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
        )
    else:
        stats = await service.process_item_ids(
            account_id,
            item_ids,
            job_id=progress.job_id,
            progress_reporter=progress,
        )

    await progress.update_metrics(
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
