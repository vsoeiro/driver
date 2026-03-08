"""Duplicate-removal job handler."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Item, ItemMetadata, LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.item_index import delete_items_by_ids
from backend.services.providers.factory import build_drive_client
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter

logger = logging.getLogger(__name__)

LOW_PRIORITY_PATH_MARKERS = (
    "/venv/",
    "/.venv/",
    "/env/",
    "/site-packages/",
    "/__pycache__/",
    "/node_modules/",
    "/.objects/",
    "/__covers__/",
)
MAX_DEDUPE_SCAN_ROWS = 200_000


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _stem_name(name: str, extension: str | None) -> str:
    clean_name = (name or "").strip()
    clean_ext = (extension or "").strip().lstrip(".")
    if not clean_ext:
        return clean_name
    suffix = f".{clean_ext}"
    if clean_name.lower().endswith(suffix.lower()):
        return clean_name[: -len(suffix)]
    return clean_name


def _is_low_priority_path(path: str | None) -> bool:
    normalized = _normalize_text(path)
    return any(marker in normalized for marker in LOW_PRIORITY_PATH_MARKERS)


def _group_should_match_scope(items: list[dict[str, Any]], scope: str) -> bool:
    account_counts: dict[UUID, int] = defaultdict(int)
    for item in items:
        account_counts[item["account_id"]] += 1
    has_same_account_matches = any(count > 1 for count in account_counts.values())
    has_cross_account_matches = len(account_counts) > 1
    if scope == "same_account":
        return has_same_account_matches
    if scope == "cross_account":
        return has_cross_account_matches
    return True


def _choose_keeper(items: list[dict[str, Any]], preferred_account_id: UUID) -> dict[str, Any]:
    return sorted(
        items,
        key=lambda item: (
            item["account_id"] != preferred_account_id,
            -(int(item.get("source_records") or 1)),
            -(int(datetime.timestamp(item["modified_at"])) if item.get("modified_at") else 0),
            str(item["account_id"]),
            item.get("path") or "",
            item.get("name") or "",
        ),
    )[0]


@register_handler("remove_duplicate_files")
async def remove_duplicate_files_handler(payload: dict, session: AsyncSession) -> dict:
    """Remove duplicate files by Similar Files filter and preferred keep-account."""
    preferred_account_id = UUID(str(payload["preferred_account_id"]))
    account_id = UUID(str(payload["account_id"])) if payload.get("account_id") else None
    scope = str(payload.get("scope") or "all")
    hide_low_priority = bool(payload.get("hide_low_priority", False))
    extensions = [
        _normalize_text(ext).lstrip(".")
        for ext in (payload.get("extensions") or [])
        if _normalize_text(ext).lstrip(".")
    ]
    ext_filter_set = set(extensions)
    progress = JobProgressReporter.from_payload(session, payload)

    stmt = select(
        Item.account_id,
        Item.item_id,
        Item.name,
        Item.path,
        Item.extension,
        Item.size,
        Item.modified_at,
    ).where(Item.item_type == "file")
    if account_id:
        stmt = stmt.where(Item.account_id == account_id)
    rows = (await session.execute(stmt.limit(MAX_DEDUPE_SCAN_ROWS + 1))).all()
    if len(rows) > MAX_DEDUPE_SCAN_ROWS:
        raise ValueError(
            f"Duplicate removal exceeded scan limit ({MAX_DEDUPE_SCAN_ROWS} files). "
            "Narrow scope by account or extensions and retry."
        )

    dedupe_map: dict[tuple[str, str, str, int, str], dict[str, Any]] = {}
    for row in rows:
        normalized_extension = _normalize_text(row.extension).lstrip(".")
        normalized_path = _normalize_text(row.path)
        dedupe_key = (
            str(row.account_id),
            normalized_path,
            _normalize_text(row.name),
            int(row.size or 0),
            normalized_extension,
        )
        current_modified = row.modified_at
        existing = dedupe_map.get(dedupe_key)
        if existing is not None:
            existing_modified = existing.get("modified_at")
            should_replace = (
                existing_modified is None
                or (current_modified is not None and current_modified > existing_modified)
            )
            if should_replace:
                existing["item_id"] = row.item_id
                existing["modified_at"] = current_modified
            existing["source_records"] = int(existing.get("source_records") or 1) + 1
            continue

        dedupe_map[dedupe_key] = {
            "account_id": row.account_id,
            "item_id": row.item_id,
            "name": row.name,
            "path": row.path,
            "extension": row.extension,
            "size": int(row.size or 0),
            "modified_at": row.modified_at,
            "source_records": 1,
        }

    entries = list(dedupe_map.values())
    with_extension_groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    without_extension_groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)

    for entry in entries:
        normalized_name = _normalize_text(entry["name"])
        normalized_extension = _normalize_text(entry["extension"]).lstrip(".")
        if ext_filter_set and normalized_extension not in ext_filter_set:
            continue
        with_extension_groups[(normalized_name, int(entry["size"] or 0), normalized_extension)].append(entry)
        stem = _normalize_text(_stem_name(entry["name"], entry["extension"]))
        without_extension_groups[(stem, int(entry["size"] or 0))].append(entry)

    groups: list[list[dict[str, Any]]] = []
    for items in with_extension_groups.values():
        if len(items) < 2:
            continue
        if not _group_should_match_scope(items, scope):
            continue
        if hide_low_priority and all(_is_low_priority_path(item.get("path")) for item in items):
            continue
        groups.append(items)

    for items in without_extension_groups.values():
        if len(items) < 2:
            continue
        extension_values = {_normalize_text(item["extension"]).lstrip(".") for item in items}
        has_blank_extension = any(not ext for ext in extension_values)
        has_extension_variation = len(extension_values) > 1
        if not has_blank_extension and not has_extension_variation:
            continue
        if not _group_should_match_scope(items, scope):
            continue
        if hide_low_priority and all(_is_low_priority_path(item.get("path")) for item in items):
            continue
        groups.append(items)

    keep_keys: set[tuple[str, str]] = set()
    candidate_keys: set[tuple[str, str]] = set()
    for group_items in groups:
        keeper = _choose_keeper(group_items, preferred_account_id)
        keep_key = (str(keeper["account_id"]), str(keeper["item_id"]))
        keep_keys.add(keep_key)
        for item in group_items:
            candidate_keys.add((str(item["account_id"]), str(item["item_id"])))

    delete_keys = [key for key in candidate_keys if key not in keep_keys]
    by_account: dict[UUID, list[str]] = defaultdict(list)
    for account_id_str, item_id in delete_keys:
        by_account[UUID(account_id_str)].append(item_id)

    total_to_delete = sum(len(item_ids) for item_ids in by_account.values())
    await progress.set_total(total_to_delete)

    if total_to_delete == 0:
        return {
            "groups_considered": len(groups),
            "planned_deletions": 0,
            "deleted": 0,
            "failed": 0,
            "failed_items": [],
        }

    accounts = (
        await session.execute(
            select(LinkedAccount).where(LinkedAccount.id.in_(list(by_account.keys())))
        )
    ).scalars().all()
    account_map = {account.id: account for account in accounts}
    token_manager = TokenManager(session)

    deleted = 0
    failed = 0
    failed_items: list[dict[str, str]] = []
    for current_account_id, item_ids in by_account.items():
        account = account_map.get(current_account_id)
        if not account:
            failed += len(item_ids)
            for item_id in item_ids[:25]:
                failed_items.append(
                    {"account_id": str(current_account_id), "item_id": item_id, "reason": "Account not found"}
                )
            continue

        client = build_drive_client(account, token_manager)
        for i in range(0, len(item_ids), 100):
            chunk = item_ids[i : i + 100]
            try:
                await client.batch_delete_items(account, chunk)
                await session.execute(
                    delete(ItemMetadata).where(
                        ItemMetadata.account_id == current_account_id,
                        ItemMetadata.item_id.in_(chunk),
                    )
                )
                await delete_items_by_ids(
                    session,
                    account_id=current_account_id,
                    item_ids=chunk,
                )
                await session.commit()
                deleted += len(chunk)
                await progress.increment(len(chunk))
            except Exception as exc:
                await session.rollback()
                failed += len(chunk)
                logger.exception("Failed to delete duplicate chunk account_id=%s size=%s", current_account_id, len(chunk))
                for item_id in chunk[:25]:
                    failed_items.append(
                        {"account_id": str(current_account_id), "item_id": item_id, "reason": str(exc)}
                    )

    await progress.update_metrics(deleted=deleted, failed=failed, groups_considered=len(groups))
    return {
        "groups_considered": len(groups),
        "planned_deletions": total_to_delete,
        "deleted": deleted,
        "failed": failed,
        "failed_items": failed_items[:50],
        "preferred_account_id": str(preferred_account_id),
    }
