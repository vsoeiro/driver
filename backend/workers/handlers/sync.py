"""Sync items job handler."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.db.models import Item, LinkedAccount
from backend.services.item_index import delete_items_by_ids, upsert_item_record
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager
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
    entries: list[SnapshotEntry] = [SnapshotEntry(item=root_item, parent_id=None, path="/")]
    errors = 0
    pages_fetched = 0
    error_items: list[dict[str, str]] = []
    error_items_truncated = 0
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
    queue.put_nowait((getattr(root_item, "id"), "/"))

    def _record_error_item(*, reason: str, item_id: str | None = None, item_name: str | None = None, stage: str | None = None) -> None:
        nonlocal error_items_truncated
        if len(error_items) >= SYNC_ERROR_ITEMS_LIMIT:
            error_items_truncated += 1
            return
        reason_text = str(reason or "Unknown error").strip() or "Unknown error"
        entry: dict[str, str] = {"reason": reason_text[:2000]}
        if item_id:
            entry["item_id"] = str(item_id)
        if item_name:
            entry["item_name"] = str(item_name)
        if stage:
            entry["stage"] = stage
        error_items.append(entry)

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
                    children = await client.list_items_by_next_link(account, children.next_link)
                    pages_fetched += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to list folder %s: %s", folder_id, exc)
                errors += 1
                _record_error_item(
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
    return entries, errors, pages_fetched, error_items, error_items_truncated


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
    entries, list_errors, pages_fetched, list_error_items, list_error_items_truncated = await _collect_provider_snapshot(
        client,
        account,
        root_item,
        worker_count=min(16, max(1, settings.worker_concurrency)),
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

    def _record_error_item(*, reason: str, item_id: str | None = None, item_name: str | None = None, stage: str | None = None) -> None:
        if len(stats["error_items"]) >= SYNC_ERROR_ITEMS_LIMIT:
            stats["error_items_truncated"] += 1
            return
        reason_text = str(reason or "Unknown error").strip() or "Unknown error"
        entry: dict[str, str] = {"reason": reason_text[:2000]}
        if item_id:
            entry["item_id"] = str(item_id)
        if item_name:
            entry["item_name"] = str(item_name)
        if stage:
            entry["stage"] = stage
        stats["error_items"].append(entry)

    existing_rows = (
        await session.execute(select(Item.item_id).where(Item.account_id == account.id))
    ).scalars().all()
    existing_ids = set(existing_rows)
    remote_ids: set[str] = set()

    for entry in entries:
        item_id = getattr(entry.item, "id")
        remote_ids.add(item_id)

        try:
            result = await upsert_item_record(
                session,
                account_id=account.id,
                item_data=entry.item,
                parent_id=entry.parent_id,
                path=entry.path,
            )
            if result == "created":
                stats["created"] += 1
            elif result == "updated":
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to upsert item %s during sync: %s", item_id, exc)
            stats["errors"] += 1
            _record_error_item(
                reason=str(exc),
                item_id=str(item_id),
                item_name=getattr(entry.item, "name", None),
                stage="upsert_item",
            )

        stats["processed"] += 1
        await progress.increment()
        if stats["processed"] % 50 == 0:
            await session.commit()
            logger.info(
                "Sync progress account_id=%s processed=%s created=%s updated=%s unchanged=%s",
                account_id,
                stats["processed"],
                stats["created"],
                stats["updated"],
                stats["unchanged"],
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
