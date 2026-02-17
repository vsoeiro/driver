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
) -> tuple[list[SnapshotEntry], int]:
    """Collect remote tree with concurrent folder listing workers."""
    entries: list[SnapshotEntry] = [SnapshotEntry(item=root_item, parent_id=None, path="/")]
    errors = 0
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
    queue.put_nowait((getattr(root_item, "id"), "/"))

    async def _worker() -> None:
        nonlocal errors
        while True:
            folder_id, folder_path = await queue.get()
            if folder_id == "__STOP__":
                queue.task_done()
                return

            try:
                children = await client.list_folder_items(account, folder_id)
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
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to list folder %s: %s", folder_id, exc)
                errors += 1
            finally:
                queue.task_done()

    workers = [asyncio.create_task(_worker()) for _ in range(max(1, worker_count))]
    await queue.join()
    for _ in workers:
        queue.put_nowait(("__STOP__", ""))
    await asyncio.gather(*workers)
    return entries, errors


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

    account = await session.get(LinkedAccount, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    token_manager = TokenManager(session)
    client = build_drive_client(account, token_manager)
    settings = get_settings()

    root_item = await client.get_item_metadata(account, "root")
    entries, list_errors = await _collect_provider_snapshot(
        client,
        account,
        root_item,
        worker_count=min(16, max(1, settings.worker_concurrency)),
    )

    stats = {
        "processed": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "deleted": 0,
        "errors": list_errors,
    }
    await progress.set_total(len(entries))

    existing_rows = (
        await session.execute(select(Item.item_id).where(Item.account_id == account.id))
    ).scalars().all()
    existing_ids = set(existing_rows)
    remote_ids: set[str] = set()

    for entry in entries:
        item_id = getattr(entry.item, "id")
        remote_ids.add(item_id)

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

        stats["processed"] += 1
        await progress.increment()
        if stats["processed"] % 50 == 0:
            await session.commit()

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
    )
    return stats
