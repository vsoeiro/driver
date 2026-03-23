"""Comic extraction job handler."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.error_items import ErrorItemsCollector
from backend.db.models import Item
from backend.services.metadata_libraries.comics.archive_conversion_service import (
    ComicArchiveConversionService,
    IndexedArchiveItem,
    validate_archive_conversion,
)
from backend.services.metadata_libraries.comics.metadata_service import ComicMetadataService, IndexedComicItem
from backend.services.metadata_libraries.implementations.comics.schema import COMICS_LIBRARY_KEY
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter

COMIC_ERROR_ITEMS_LIMIT = 50


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


async def _load_indexed_items(
    session: AsyncSession,
    *,
    account_id: UUID,
    item_ids: list[str],
) -> list[IndexedComicItem]:
    stmt = select(Item.item_id, Item.name, Item.extension, Item.item_type, Item.size).where(
        Item.account_id == account_id,
        Item.item_id.in_(item_ids),
        Item.item_type == "file",
    )
    rows = (await session.execute(stmt)).all()
    return [
        IndexedComicItem(
            id=str(item_id),
            name=str(name or item_id),
            extension=str(extension).lower() if extension else None,
            item_type=str(item_type or "file"),
            size=int(size) if size is not None else None,
        )
        for item_id, name, extension, item_type, size in rows
    ]


async def _load_indexed_archive_items(
    session: AsyncSession,
    *,
    account_id: UUID,
    item_ids: list[str],
) -> list[IndexedArchiveItem]:
    stmt = select(
        Item.item_id,
        Item.name,
        Item.extension,
        Item.item_type,
        Item.parent_id,
        Item.path,
        Item.size,
    ).where(
        Item.account_id == account_id,
        Item.item_id.in_(item_ids),
        Item.item_type == "file",
    )
    rows = (await session.execute(stmt)).all()
    return [
        IndexedArchiveItem(
            id=str(item_id),
            name=str(name or item_id),
            extension=str(extension).lower() if extension else None,
            item_type=str(item_type or "file"),
            parent_id=str(parent_id) if parent_id is not None else None,
            path=str(path) if path is not None else None,
            size=int(size) if size is not None else None,
        )
        for item_id, name, extension, item_type, parent_id, path, size in rows
    ]


async def _process_indexed_item_groups(
    payload: dict,
    *,
    session: AsyncSession,
    service: ComicMetadataService,
    progress: JobProgressReporter,
    force_remap: bool = False,
) -> dict:
    item_groups = _normalize_indexed_item_groups(payload)
    if not item_groups:
        return {"total": 0, "mapped": 0, "skipped": 0, "failed": 0}

    total_requested = sum(len(item_ids) for _account_id, item_ids in item_groups)
    await progress.set_total(total_requested)

    stats = {
        "total": 0,
        "mapped": 0,
        "skipped": 0,
        "failed": 0,
        "accounts": len(item_groups),
        "error_items": [],
        "error_items_truncated": 0,
    }
    error_collector = ErrorItemsCollector(stats, limit=COMIC_ERROR_ITEMS_LIMIT)

    for account_id, item_ids in item_groups:
        indexed_items = await _load_indexed_items(
            session,
            account_id=account_id,
            item_ids=item_ids,
        )
        account_stats = await service.process_indexed_items(
            account_id,
            indexed_items,
            job_id=progress.job_id,
            progress_reporter=progress,
            initialize_progress_total=False,
            force_remap=force_remap,
        )
        stats["total"] += account_stats.get("total", 0)
        stats["mapped"] += account_stats.get("mapped", 0)
        stats["skipped"] += account_stats.get("skipped", 0)
        stats["failed"] += account_stats.get("failed", 0)
        error_collector.merge(account_stats)

    return stats


@register_handler("extract_comic_assets")
async def extract_comic_assets_handler(payload: dict, session: AsyncSession) -> dict:
    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    service = ComicMetadataService(session)
    indexed_groups = _normalize_indexed_item_groups(payload)
    if indexed_groups:
        stats = await _process_indexed_item_groups(
            payload,
            session=session,
            service=service,
            progress=progress,
        )
    else:
        account_id = UUID(payload["account_id"])
        item_ids = [str(item_id) for item_id in payload.get("item_ids", [])]
        if not item_ids:
            return {"total": 0, "mapped": 0, "skipped": 0, "failed": 0}

        await progress.set_total(len(item_ids))
        if payload.get("use_indexed_items"):
            indexed = await _load_indexed_items(
                session,
                account_id=account_id,
                item_ids=item_ids,
            )
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
    service = ComicMetadataService(session)
    indexed_groups = _normalize_indexed_item_groups(payload)
    if indexed_groups:
        stats = await _process_indexed_item_groups(
            payload,
            session=session,
            service=service,
            progress=progress,
            force_remap=True,
        )
    else:
        await progress.set_total(1)
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
    error_collector = ErrorItemsCollector(stats, limit=COMIC_ERROR_ITEMS_LIMIT)
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
        error_collector.merge(account_stats)

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


@register_handler("convert_library_comic_archives")
async def convert_library_comic_archives_handler(payload: dict, session: AsyncSession) -> dict:
    source_format, target_format = validate_archive_conversion(
        payload.get("source_format"),
        payload.get("target_format"),
    )
    delete_source_after_convert = bool(payload.get("delete_source_after_convert"))
    progress = JobProgressReporter.from_payload(session, payload)
    progress.flush_every_items = 5
    item_groups = _normalize_indexed_item_groups(payload)
    total_requested = sum(len(item_ids) for _account_id, item_ids in item_groups)
    await progress.set_total(total_requested)

    service = ComicArchiveConversionService(session)
    stats = {
        "total": total_requested,
        "converted": 0,
        "skipped": 0,
        "failed": 0,
        "accounts": len(item_groups),
        "source_format": source_format,
        "target_format": target_format,
        "deleted_source": 0,
        "error_items": [],
        "error_items_truncated": 0,
    }
    error_collector = ErrorItemsCollector(stats, limit=COMIC_ERROR_ITEMS_LIMIT)

    for account_id, item_ids in item_groups:
        indexed_items = await _load_indexed_archive_items(
            session,
            account_id=account_id,
            item_ids=item_ids,
        )
        account_stats = await service.convert_indexed_items(
            account_id=account_id,
            indexed_items=indexed_items,
            source_format=source_format,
            target_format=target_format,
            delete_source_after_convert=delete_source_after_convert,
            progress_reporter=progress,
        )
        stats["converted"] += account_stats.get("converted", 0)
        stats["skipped"] += account_stats.get("skipped", 0)
        stats["failed"] += account_stats.get("failed", 0)
        stats["deleted_source"] += account_stats.get("deleted_source", 0)
        error_collector.merge(account_stats)

    await session.commit()
    await progress.update_metrics(
        converted=stats["converted"],
        skipped=stats["skipped"],
        failed=stats["failed"],
        accounts=stats["accounts"],
        source_format=source_format,
        target_format=target_format,
        deleted_source=stats["deleted_source"],
        error_items=stats.get("error_items", []),
        error_items_truncated=stats.get("error_items_truncated", 0),
    )
    progress.current = total_requested
    await progress.flush(force=True)
    return stats
