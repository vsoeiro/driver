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
from backend.services.metadata_libraries.implementations.books.schema import BOOKS_LIBRARY_KEY
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter


def _normalize_indexed_item_groups(payload: dict) -> list[tuple[UUID, list[str]]]:
    raw_groups = payload.get("indexed_item_groups")
    if not isinstance(raw_groups, list):
        return []

    normalized: list[tuple[UUID, list[str]]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict):
            continue
        try:
            account_id = UUID(str(raw_group.get("account_id")))
        except (TypeError, ValueError):
            continue
        item_ids = [
            str(item_id)
            for item_id in (raw_group.get("item_ids") or [])
            if str(item_id).strip()
        ]
        if item_ids:
            normalized.append((account_id, item_ids))
    return normalized


@register_handler("extract_book_assets")
async def extract_book_assets_handler(payload: dict, session: AsyncSession) -> dict:
    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    service = BookMetadataService(session)
    indexed_groups = _normalize_indexed_item_groups(payload)
    if indexed_groups:
        total_requested = sum(len(item_ids) for _account_id, item_ids in indexed_groups)
        await progress.set_total(total_requested)
        stats = {"total": 0, "mapped": 0, "skipped": 0, "failed": 0, "error_items": [], "error_items_truncated": 0}
        for account_id, item_ids in indexed_groups:
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
            account_stats = await service.process_indexed_items(
                account_id,
                indexed,
                job_id=progress.job_id,
                progress_reporter=progress,
                initialize_progress_total=False,
            )
            stats["total"] += account_stats["total"]
            stats["mapped"] += account_stats["mapped"]
            stats["skipped"] += account_stats["skipped"]
            stats["failed"] += account_stats["failed"]
            stats["error_items"].extend(account_stats.get("error_items", []))
            stats["error_items_truncated"] += account_stats.get("error_items_truncated", 0)
    else:
        account_id = UUID(payload["account_id"])
        item_ids = [str(item_id) for item_id in payload.get("item_ids", [])]
        if not item_ids:
            return {"total": 0, "mapped": 0, "skipped": 0, "failed": 0}
        await progress.set_total(len(item_ids))
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


@register_handler("reindex_book_covers")
async def reindex_book_covers_handler(payload: dict, session: AsyncSession) -> dict:
    library_key = payload.get("library_key") or payload.get("plugin_key") or BOOKS_LIBRARY_KEY
    if library_key != BOOKS_LIBRARY_KEY:
        raise ValueError("Unsupported metadata library key for book cover reindex")

    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    service = BookMetadataService(session)
    indexed_groups = _normalize_indexed_item_groups(payload)
    if indexed_groups:
        total_requested = sum(len(item_ids) for _account_id, item_ids in indexed_groups)
        await progress.set_total(total_requested)
        stats = {"total": 0, "mapped": 0, "skipped": 0, "failed": 0, "error_items": [], "error_items_truncated": 0}
        for account_id, item_ids in indexed_groups:
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
            account_stats = await service.process_indexed_items(
                account_id,
                indexed,
                job_id=progress.job_id,
                progress_reporter=progress,
                initialize_progress_total=False,
                force_remap=True,
            )
            stats["total"] += account_stats["total"]
            stats["mapped"] += account_stats["mapped"]
            stats["skipped"] += account_stats["skipped"]
            stats["failed"] += account_stats["failed"]
            stats["error_items"].extend(account_stats.get("error_items", []))
            stats["error_items_truncated"] += account_stats.get("error_items_truncated", 0)
    else:
        await progress.set_total(1)
        stats = await service.reindex_mapped_books(job_id=progress.job_id)

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
