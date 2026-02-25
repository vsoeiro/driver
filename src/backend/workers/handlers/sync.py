"""Sync items job handler."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.error_items import ErrorItemsCollector
from backend.core.config import get_settings
from backend.db.models import LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.item_index import (
    build_item_payload,
    build_item_signature_from_payload,
    bulk_upsert_item_payloads,
    delete_items_by_ids,
    fetch_item_signatures_by_item_id,
)
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter

logger = logging.getLogger(__name__)
SYNC_ERROR_ITEMS_LIMIT = 50


@dataclass
class SnapshotEntry:
    """Flat item snapshot entry used by the incremental reconcile phase."""

    item: object
    parent_id: str | None
    path: str


def _build_child_path(parent_path: str, name: str) -> str:
    if parent_path == "/":
        return f"/{name}"
    return f"{parent_path.rstrip('/')}/{name}"


async def _collect_provider_snapshot(
    client: DriveProviderClient,
    account: LinkedAccount,
    root_item: object,
    *,
    worker_count: int,
) -> tuple[list[SnapshotEntry], int, int, list[dict[str, str]], int]:
    """Collect remote tree with concurrent folder listing workers."""
    entries: list[SnapshotEntry] = [
        SnapshotEntry(item=root_item, parent_id=None, path="/")
    ]
    errors = 0
    pages_fetched = 0
    error_stats: dict[str, object] = {
        "error_items": [],
        "error_items_truncated": 0,
    }
    error_collector = ErrorItemsCollector(error_stats, limit=SYNC_ERROR_ITEMS_LIMIT)
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
    queue.put_nowait((getattr(root_item, "id"), "/"))

    async def _worker() -> None:
        nonlocal errors
        nonlocal pages_fetched
        while True:
            folder_id, folder_path = await queue.get()
            if folder_id == "__STOP__":
                queue.task_done()
                return

            try:
                children = await client.list_folder_items(account, folder_id)
                pages_fetched += 1
                while True:
                    for child in children.items:
                        child_path = _build_child_path(folder_path, child.name)
                        entries.append(
                            SnapshotEntry(
                                item=child,
                                parent_id=folder_id,
                                path=child_path,
                            )
                        )
                        if child.item_type == "folder":
                            queue.put_nowait((child.id, child_path))
                    if not children.next_link:
                        break
                    children = await client.list_items_by_next_link(
                        account, children.next_link
                    )
                    pages_fetched += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to list folder %s: %s", folder_id, exc)
                errors += 1
                error_collector.record(
                    reason=str(exc),
                    item_id=str(folder_id),
                    stage="list_folder",
                )
            finally:
                queue.task_done()

    workers = [asyncio.create_task(_worker()) for _ in range(max(1, worker_count))]
    await queue.join()
    for _ in workers:
        queue.put_nowait(("__STOP__", ""))
    await asyncio.gather(*workers)
    return (
        entries,
        errors,
        pages_fetched,
        error_stats.get("error_items", []),
        int(error_stats.get("error_items_truncated", 0) or 0),
    )


@register_handler("sync_items")
async def sync_items_handler(payload: dict, session: AsyncSession) -> dict:
    """Handle sync items job.

    Payload structure:
    {
        "account_id": "uuid"
    }
    """
    account_id = UUID(payload["account_id"])
    progress = JobProgressReporter.from_payload(session, payload)
    logger.info("Sync job started account_id=%s job_id=%s", account_id, progress.job_id)

    account = await session.get(LinkedAccount, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    token_manager = TokenManager(session)
    client = build_drive_client(account, token_manager)
    settings = get_settings()

    root_item = await client.get_item_metadata(account, "root")
    (
        entries,
        list_errors,
        pages_fetched,
        list_error_items,
        list_error_items_truncated,
    ) = await _collect_provider_snapshot(
        client,
        account,
        root_item,
        worker_count=(
            min(
                max(1, settings.sync_snapshot_worker_count_microsoft),
                max(1, settings.worker_concurrency),
            )
            if (account.provider or "").lower() == "microsoft"
            else min(
                max(1, settings.sync_snapshot_worker_count),
                max(1, settings.worker_concurrency),
            )
        ),
    )
    logger.info(
        "Sync snapshot collected account_id=%s entries=%s listing_errors=%s pages_fetched=%s",
        account_id,
        len(entries),
        list_errors,
        pages_fetched,
    )

    stats = {
        "processed": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "deleted": 0,
        "errors": list_errors,
        "pages_fetched": pages_fetched,
        "error_items": list_error_items,
        "error_items_truncated": list_error_items_truncated,
    }
    await progress.set_total(len(entries))
    error_collector = ErrorItemsCollector(stats, limit=SYNC_ERROR_ITEMS_LIMIT)

    existing_signatures = await fetch_item_signatures_by_item_id(
        session,
        account_id=account.id,
    )
    existing_ids = set(existing_signatures.keys())
    remote_ids: set[str] = set()
    pending_upsert_payloads: list[dict] = []
    upsert_batch_size = 500

    for entry in entries:
        item_id = str(getattr(entry.item, "id"))
        remote_ids.add(item_id)

        try:
            payload = build_item_payload(
                account_id=account.id,
                item_data=entry.item,
                parent_id=entry.parent_id,
                path=entry.path,
            )
            new_signature = build_item_signature_from_payload(payload)
            old_signature = existing_signatures.get(item_id)
            if old_signature is None:
                stats["created"] += 1
                pending_upsert_payloads.append(payload)
            elif old_signature != new_signature:
                stats["updated"] += 1
                pending_upsert_payloads.append(payload)
            else:
                stats["unchanged"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to upsert item %s during sync: %s", item_id, exc)
            stats["errors"] += 1
            error_collector.record(
                reason=str(exc),
                item_id=str(item_id),
                item_name=getattr(entry.item, "name", None),
                stage="upsert_item",
            )

        stats["processed"] += 1
        await progress.increment()
        if len(pending_upsert_payloads) >= upsert_batch_size:
            await bulk_upsert_item_payloads(
                session,
                payloads=pending_upsert_payloads,
                chunk_size=upsert_batch_size,
            )
            pending_upsert_payloads.clear()
        if stats["processed"] % 50 == 0:
            if pending_upsert_payloads:
                await bulk_upsert_item_payloads(
                    session,
                    payloads=pending_upsert_payloads,
                    chunk_size=upsert_batch_size,
                )
                pending_upsert_payloads.clear()
            await session.commit()
            logger.info(
                "Sync progress account_id=%s processed=%s created=%s updated=%s unchanged=%s",
                account_id,
                stats["processed"],
                stats["created"],
                stats["updated"],
                stats["unchanged"],
            )

    if pending_upsert_payloads:
        await bulk_upsert_item_payloads(
            session,
            payloads=pending_upsert_payloads,
            chunk_size=upsert_batch_size,
        )

    stale_ids = list(existing_ids - remote_ids)
    if stale_ids:
        stats["deleted"] = await delete_items_by_ids(
            session,
            account_id=account.id,
            item_ids=stale_ids,
        )

    await session.commit()
    await progress.update_metrics(
        processed=stats["processed"],
        created=stats["created"],
        updated=stats["updated"],
        unchanged=stats["unchanged"],
        deleted=stats["deleted"],
        errors=stats["errors"],
        pages_fetched=stats["pages_fetched"],
    )
    logger.info("Sync job completed account_id=%s stats=%s", account_id, stats)
    return stats
