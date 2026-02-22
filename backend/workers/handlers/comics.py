"""Comic extraction job handler."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Item
from backend.services.comics import ComicMetadataService, IndexedComicItem
from backend.services.metadata_plugins import COMICS_LIBRARY_KEY
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter

COMIC_ERROR_ITEMS_LIMIT = 50


def _record_error_item(
    stats: dict,
    *,
    reason: str,
    item_id: str | None = None,
    item_name: str | None = None,
    account_id: str | None = None,
) -> None:
    error_items = stats.get("error_items")
    if not isinstance(error_items, list):
        error_items = []
        stats["error_items"] = error_items

    if len(error_items) >= COMIC_ERROR_ITEMS_LIMIT:
        stats["error_items_truncated"] = int(stats.get("error_items_truncated", 0) or 0) + 1
        return

    reason_text = str(reason or "Unknown error").strip() or "Unknown error"
    entry: dict[str, str] = {"reason": reason_text[:2000]}
    if item_id:
        entry["item_id"] = str(item_id)
    if item_name:
        entry["item_name"] = str(item_name)
    if account_id:
        entry["account_id"] = str(account_id)
    error_items.append(entry)


def _merge_error_items(target: dict, source: dict) -> None:
    source_items = source.get("error_items")
    if isinstance(source_items, list):
        for raw in source_items:
            if not isinstance(raw, dict):
                continue
            _record_error_item(
                target,
                reason=str(raw.get("reason") or "Unknown error"),
                item_id=str(raw.get("item_id")) if raw.get("item_id") else None,
                item_name=str(raw.get("item_name")) if raw.get("item_name") else None,
                account_id=str(raw.get("account_id")) if raw.get("account_id") else None,
            )
    target["error_items_truncated"] = int(target.get("error_items_truncated", 0) or 0) + int(
        source.get("error_items_truncated", 0) or 0
    )


@register_handler("extract_comic_assets")
async def extract_comic_assets_handler(payload: dict, session: AsyncSession) -> dict:
    account_id = UUID(payload["account_id"])
    item_ids = [str(item_id) for item_id in payload.get("item_ids", [])]
    if not item_ids:
        return {"total": 0, "mapped": 0, "skipped": 0, "failed": 0}

    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    await progress.set_total(len(item_ids))

    service = ComicMetadataService(session)
    if payload.get("use_indexed_items"):
        stmt = select(Item.item_id, Item.name, Item.extension, Item.item_type, Item.size).where(
            Item.account_id == account_id,
            Item.item_id.in_(item_ids),
            Item.item_type == "file",
        )
        rows = (await session.execute(stmt)).all()
        indexed = [
            IndexedComicItem(
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
    await session.commit()

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


@register_handler("reindex_comic_covers")
async def reindex_comic_covers_handler(payload: dict, session: AsyncSession) -> dict:
    library_key = payload.get("library_key") or payload.get("plugin_key") or COMICS_LIBRARY_KEY
    if library_key != COMICS_LIBRARY_KEY:
        raise ValueError("Unsupported metadata library key for cover reindex")

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
        error_items=stats.get("error_items", []),
        error_items_truncated=stats.get("error_items_truncated", 0),
    )
    await progress.set_total(max(1, stats.get("total", 0)))
    progress.current = max(1, stats.get("total", 0))
    await progress.flush()

    return stats


@register_handler("extract_library_comic_assets")
async def extract_library_comic_assets_handler(payload: dict, session: AsyncSession) -> dict:
    account_ids = payload.get("account_ids") or []
    normalized_account_ids = []
    for raw_id in account_ids:
        try:
            normalized_account_ids.append(UUID(str(raw_id)))
        except ValueError:
            continue

    stmt = select(Item.account_id, Item.item_id, Item.name, Item.extension, Item.size).where(
        Item.item_type == "file",
        func.lower(func.coalesce(Item.extension, "")).in_(("cbr", "cbz")),
    )
    if normalized_account_ids:
        stmt = stmt.where(Item.account_id.in_(normalized_account_ids))

    result = await session.execute(stmt)
    rows = result.all()
    if not rows:
        return {"total": 0, "mapped": 0, "skipped": 0, "failed": 0, "accounts": 0}

    by_account: dict[UUID, list[IndexedComicItem]] = {}
    for account_id, item_id, name, extension, size in rows:
        by_account.setdefault(account_id, []).append(
            IndexedComicItem(
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

    service = ComicMetadataService(session)
    stats = {
        "total": len(rows),
        "mapped": 0,
        "skipped": 0,
        "failed": 0,
        "accounts": len(by_account),
        "error_items": [],
        "error_items_truncated": 0,
    }
    for account_id, indexed_items in by_account.items():
        account_stats = await service.process_indexed_items(
            account_id,
            indexed_items,
            job_id=progress.job_id,
            progress_reporter=progress,
            initialize_progress_total=False,
        )
        stats["mapped"] += account_stats.get("mapped", 0)
        stats["skipped"] += account_stats.get("skipped", 0)
        stats["failed"] += account_stats.get("failed", 0)
        _merge_error_items(stats, account_stats)

    await session.commit()
    await progress.update_metrics(
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
