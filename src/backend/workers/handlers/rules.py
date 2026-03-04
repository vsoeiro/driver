"""Automatic metadata rule job handlers."""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.metadata.repositories import ItemMetadataRepository
from backend.application.drive.transfer_service import DriveTransferService
from backend.common.error_items import ErrorItemsCollector
from backend.db.models import (
    Item,
    LinkedAccount,
    MetadataAttribute,
    MetadataRule,
)
from backend.security.token_manager import TokenManager
from backend.services.item_index import (
    delete_item_and_descendants,
    parent_id_from_breadcrumb,
    path_from_breadcrumb,
    update_descendant_paths,
    upsert_item_record,
)
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.providers.factory import build_drive_client
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter

logger = logging.getLogger(__name__)
ERROR_ITEMS_LIMIT = 50

TOKEN_PATTERN = re.compile(r"\[([^\[\]]+)\]")


def _build_rule_item_query(rule: MetadataRule):
    query = select(Item).where(Item.path.isnot(None))
    if rule.account_id:
        query = query.where(Item.account_id == rule.account_id)
    if rule.path_prefix:
        prefix = rule.path_prefix.rstrip("/")
        query = query.where(Item.path.ilike(f"{prefix}/%"))
    if rule.path_contains:
        query = query.where(Item.path.ilike(f"%{rule.path_contains}%"))
    if not rule.include_folders:
        query = query.where(Item.item_type == "file")
    return query.order_by(Item.path.asc())


def _normalize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", without_accents.strip().upper())
    return cleaned.strip("_")


def _sanitize_name(value: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', " ", value).strip().strip(".")
    return re.sub(r"\s{2,}", " ", sanitized)


def _sanitize_path_segment(value: str) -> str:
    return _sanitize_name(value).replace("/", " ").replace("\\", " ").strip()


def _render_template(template: str | None, context: dict[str, str]) -> str:
    if not template:
        return ""

    def _replace(match: re.Match[str]) -> str:
        token = _normalize_token(match.group(1))
        return context.get(token, "")

    rendered = TOKEN_PATTERN.sub(_replace, template)
    rendered = re.sub(r"\s{2,}", " ", rendered).strip()
    return rendered


def _build_placeholder_context(
    *,
    item: Item,
    metadata_values: dict[str, Any],
    attributes_by_id: dict[str, MetadataAttribute],
) -> dict[str, str]:
    context: dict[str, str] = {}
    for attr_id, raw_value in metadata_values.items():
        attr = attributes_by_id.get(str(attr_id))
        if attr is None:
            continue
        text_value = "" if raw_value is None else str(raw_value)
        name_key = _normalize_token(attr.name)
        if name_key:
            context[name_key] = text_value
        if attr.plugin_field_key:
            plugin_key = _normalize_token(attr.plugin_field_key)
            if plugin_key:
                context[plugin_key] = text_value

    extension = (item.extension or "").strip(".")
    name = item.name or ""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    context.update(
        {
            "EXT": extension,
            "EXTENSAO": extension,
            "EXTENSION": extension,
            "NOME_ATUAL": name,
            "CURRENT_NAME": name,
            "STEM": stem,
            "ITEM_ID": item.item_id,
        }
    )
    return context


async def _find_or_create_folder(
    *,
    client,
    account: LinkedAccount,
    parent_id: str,
    folder_name: str,
) -> str:
    listing = await client.list_folder_items(account, parent_id)
    while True:
        for child in listing.items:
            if child.item_type == "folder" and child.name == folder_name:
                return child.id
        if not listing.next_link:
            break
        listing = await client.list_items_by_next_link(account, listing.next_link)

    created = await client.create_folder(
        account, folder_name, parent_id=parent_id, conflict_behavior="rename"
    )
    return created.id


async def _resolve_destination_folder_id(
    *,
    client,
    account: LinkedAccount,
    base_folder_id: str,
    path_template: str,
    context: dict[str, str],
    cache: dict[tuple[str, str, str], str],
) -> str:
    current_parent = base_folder_id or "root"
    rendered_path = _render_template(path_template, context).strip().strip("/\\")
    if not rendered_path:
        return current_parent

    segments = [seg for seg in re.split(r"[\\/]+", rendered_path) if seg]
    for raw_segment in segments:
        segment = _sanitize_path_segment(raw_segment)
        if not segment:
            continue
        cache_key = (str(account.id), current_parent, segment)
        cached = cache.get(cache_key)
        if cached:
            current_parent = cached
            continue
        next_parent = await _find_or_create_folder(
            client=client,
            account=account,
            parent_id=current_parent,
            folder_name=segment,
        )
        cache[cache_key] = next_parent
        current_parent = next_parent

    return current_parent


@register_handler("apply_metadata_rule")
async def apply_metadata_rule_handler(payload: dict, session: AsyncSession) -> dict:
    """Apply a metadata rule to matching items."""
    rule_id = UUID(payload["rule_id"])
    batch_id = (
        UUID(payload.get("batch_id")) if payload.get("batch_id") else uuid.uuid4()
    )
    progress = JobProgressReporter.from_payload(session, payload)

    rule = await session.get(MetadataRule, rule_id)
    if not rule:
        raise ValueError(f"Rule {rule_id} not found")

    query = _build_rule_item_query(rule)
    result = await session.execute(query)
    items = result.scalars().all()
    metadata_repo = ItemMetadataRepository(session)
    metadata_by_item_id = await metadata_repo.get_by_items(
        account_id=rule.account_id,
        item_ids=[item.item_id for item in items],
    ) if rule.account_id else await metadata_repo.get_by_account_item_pairs(
        pairs=[(item.account_id, item.item_id) for item in items]
    )

    await progress.set_total(len(items))

    stats = {
        "total": len(items),
        "changed": 0,
        "skipped": 0,
        "errors": 0,
        "batch_id": str(batch_id),
        "error_items": [],
        "error_items_truncated": 0,
    }
    error_collector = ErrorItemsCollector(stats, limit=ERROR_ITEMS_LIMIT)
    transfer_service = DriveTransferService()
    batch_count = 0
    token_manager = TokenManager(session)
    account_cache: dict[UUID, LinkedAccount] = {}
    client_cache: dict[UUID, Any] = {}
    folder_cache: dict[tuple[str, str, str], str] = {}

    attr_rows = await session.execute(
        select(MetadataAttribute).where(
            MetadataAttribute.category_id == rule.target_category_id
        )
    )
    attributes_by_id = {str(attr.id): attr for attr in attr_rows.scalars().all()}

    async def _get_account(account_id: UUID) -> LinkedAccount:
        account = account_cache.get(account_id)
        if account is None:
            account = await session.get(LinkedAccount, account_id)
            if account is None:
                raise ValueError(f"Linked account {account_id} not found")
            account_cache[account_id] = account
        return account

    async def _get_client(account_id: UUID):
        client = client_cache.get(account_id)
        if client is None:
            account = await _get_account(account_id)
            client = build_drive_client(account, token_manager)
            client_cache[account_id] = client
        return client

    for item in items:
        try:
            item_changed = False
            normalized_rule_values = rule.target_values or {}
            if rule.account_id:
                current_metadata = metadata_by_item_id.get(item.item_id)
            else:
                current_metadata = metadata_by_item_id.get(
                    (item.account_id, item.item_id)
                )

            change = (
                await apply_metadata_change(
                    session,
                    account_id=item.account_id,
                    item_id=item.item_id,
                    category_id=(
                        rule.target_category_id if rule.apply_metadata else None
                    ),
                    values=(
                        normalized_rule_values
                        if rule.apply_metadata
                        else None
                    ),
                    batch_id=batch_id,
                    job_id=progress.job_id,
                )
                if (rule.apply_metadata or rule.apply_remove_metadata)
                else {"changed": False}
            )

            if change.get("changed"):
                item_changed = True

            if rule.apply_rename or rule.apply_move:
                if (
                    current_metadata is None
                    or current_metadata.category_id != rule.target_category_id
                ):
                    stats["skipped"] += 1
                    continue

                metadata_values = dict(current_metadata.values or {})
                if rule.apply_metadata:
                    metadata_values.update(normalized_rule_values)
                context = _build_placeholder_context(
                    item=item,
                    metadata_values=metadata_values,
                    attributes_by_id=attributes_by_id,
                )

                new_name: str | None = None
                if rule.apply_rename:
                    rendered_name = _render_template(rule.rename_template, context)
                    rendered_name = _sanitize_name(rendered_name)
                    if not rendered_name:
                        raise ValueError("Rendered rename template is empty")
                    if (
                        item.item_type == "file"
                        and "." not in rendered_name
                        and item.extension
                    ):
                        rendered_name = f"{rendered_name}.{item.extension}"
                    new_name = rendered_name

                destination_parent_id: str | None = None
                destination_account_id = rule.destination_account_id or item.account_id
                if rule.apply_move:
                    destination_account = await _get_account(destination_account_id)
                    destination_client = await _get_client(destination_account_id)
                    destination_parent_id = await _resolve_destination_folder_id(
                        client=destination_client,
                        account=destination_account,
                        base_folder_id=rule.destination_folder_id or "root",
                        path_template=rule.destination_path_template or "",
                        context=context,
                        cache=folder_cache,
                    )

                if rule.apply_move and destination_account_id != item.account_id:
                    if item.item_type != "file":
                        raise ValueError(
                            "Cross-account move is only supported for files"
                        )

                    source_account = await _get_account(item.account_id)
                    source_client = await _get_client(item.account_id)
                    destination_account = await _get_account(destination_account_id)
                    destination_client = await _get_client(destination_account_id)
                    source_item = await source_client.get_item_metadata(
                        source_account, item.item_id
                    )
                    new_item_id = await transfer_service.transfer_file_between_accounts(
                        source_client=source_client,
                        destination_client=destination_client,
                        source_account=source_account,
                        destination_account=destination_account,
                        source_item_id=source_item.id,
                        source_item_name=source_item.name,
                        destination_folder_id=destination_parent_id or "root",
                    )
                    await delete_item_and_descendants(
                        session,
                        account_id=item.account_id,
                        item_id=item.item_id,
                    )
                    if new_item_id:
                        updated_meta = await destination_client.get_item_metadata(
                            destination_account, new_item_id
                        )
                        if new_name and updated_meta.name != new_name:
                            updated_meta = await destination_client.update_item(
                                destination_account,
                                updated_meta.id,
                                name=new_name,
                            )
                        breadcrumb = await destination_client.get_item_path(
                            destination_account, updated_meta.id
                        )
                        await upsert_item_record(
                            session,
                            account_id=destination_account.id,
                            item_data=updated_meta,
                            parent_id=parent_id_from_breadcrumb(breadcrumb),
                            path=path_from_breadcrumb(breadcrumb),
                        )
                        item_changed = True
                elif rule.apply_move or rule.apply_rename:
                    source_account = await _get_account(item.account_id)
                    source_client = await _get_client(item.account_id)
                    old_path = item.path
                    updated_item = await source_client.update_item(
                        source_account,
                        item.item_id,
                        name=new_name if rule.apply_rename else None,
                        parent_id=destination_parent_id if rule.apply_move else None,
                    )
                    breadcrumb = await source_client.get_item_path(
                        source_account, updated_item.id
                    )
                    new_path = path_from_breadcrumb(breadcrumb)
                    await upsert_item_record(
                        session,
                        account_id=source_account.id,
                        item_data=updated_item,
                        parent_id=parent_id_from_breadcrumb(breadcrumb),
                        path=new_path,
                    )
                    if (
                        updated_item.item_type == "folder"
                        and old_path
                        and old_path != new_path
                    ):
                        await update_descendant_paths(
                            session,
                            account_id=source_account.id,
                            old_prefix=old_path,
                            new_prefix=new_path,
                        )
                    item_changed = True

            if item_changed:
                stats["changed"] += 1
            else:
                stats["skipped"] += 1
            batch_count += 1
            if batch_count >= 200:
                await session.commit()
                batch_count = 0
        except Exception as exc:
            logger.error("Rule %s failed for item %s: %s", rule_id, item.item_id, exc)
            stats["errors"] += 1
            error_collector.record(
                reason=str(exc),
                item_id=item.item_id,
                item_name=item.name,
                stage="apply_rule",
            )
        finally:
            await progress.increment()
            if progress.current % 10 == 0:
                await progress.update_metrics(
                    changed=stats["changed"],
                    skipped=stats["skipped"],
                    errors=stats["errors"],
                )

    if batch_count > 0:
        await session.commit()

    return stats


@register_handler("undo_metadata_batch")
async def undo_metadata_batch_handler(payload: dict, session: AsyncSession) -> dict:
    """Undo metadata changes from an earlier batch id."""
    from backend.services.metadata_versioning import undo_metadata_batch

    batch_id = UUID(payload["batch_id"])
    progress = JobProgressReporter.from_payload(session, payload)
    # Undo iterates full batch; total is unknown before query inside service.
    await progress.set_total(None)
    result = await undo_metadata_batch(
        session,
        batch_id=batch_id,
        job_id=progress.job_id,
    )
    await progress.update_metrics(**result)
    return result
