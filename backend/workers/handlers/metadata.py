"""Metadata update job handler."""

import logging
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Item, ItemMetadata, LinkedAccount, MetadataAttribute, MetadataCategory
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.item_index import upsert_item_record
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager
from backend.workers.job_progress import JobProgressReporter
from backend.workers.dispatcher import register_handler

logger = logging.getLogger(__name__)


@register_handler("update_metadata")
async def update_metadata_handler(payload: dict, session: AsyncSession) -> dict:
    """Handle bulk metadata update job.

    Payload structure:
    {
        "account_id": "uuid",
        "root_item_id": "str",
        "metadata": {"attribute_name": "value"},
        "category_name": "str"
    }
    """
    account_id = UUID(payload["account_id"])
    root_item_id = payload["root_item_id"]
    metadata_updates = payload["metadata"]
    category_name = payload["category_name"]
    progress = JobProgressReporter.from_payload(session, payload)
    batch_id = uuid.UUID(payload.get("batch_id")) if payload.get("batch_id") else uuid.uuid4()

    # 1. Fetch account
    account = await session.get(LinkedAccount, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    # 2. Fetch category and attributes to validate
    stmt = select(MetadataCategory).where(MetadataCategory.name == category_name)
    result = await session.execute(stmt)
    category = result.scalar_one_or_none()

    if not category:
        # Create category if it doesn't exist? Or fail?
        # For now, let's assume it must exist or we create it?
        # The user request implies "cbr_type" and "comic", which might be categories or attributes.
        # "Selecionei uma pasta, alterei os metadados..."
        # Let's fail if not found for strictness, or maybe we auto-create.
        # Given "alterei os metadados", implied they exist.
        raise ValueError(f"Metadata category {category_name} not found")

    # Resolve attribute names to IDs
    # We need to map payload keys (attribute names) to attribute IDs for storage
    # defined in ItemMetadata.values
    
    # Pre-fetch attributes for this category
    stmt = select(MetadataAttribute).where(MetadataAttribute.category_id == category.id)
    result = await session.execute(stmt)
    attributes = result.scalars().all()
    attr_map = {attr.name: attr.id for attr in attributes}

    # Validate and prepare update dict
    # Key: Attribute ID (str), Value: Value
    metadata_values_to_set = {}
    for key, value in metadata_updates.items():
        if key in attr_map:
            metadata_values_to_set[str(attr_map[key])] = value
        else:
            logger.warning(f"Attribute {key} not found in category {category_name}, skipping.")

    token_manager = TokenManager(session)
    client = build_drive_client(account, token_manager)

    # 3. Start recursive update
    stats = {"processed": 0, "updated": 0, "errors": 0, "batch_id": str(batch_id)}
    
    # Check root item type
    root_item = await client.get_item_metadata(account, root_item_id)
    
    # Resolve root path (best effort, or just name if root)
    # We could fetch full path via Graph, but for now let's start with root item name?
    # Or maybe we don't strictly need path for the root if it's too expensive.
    # Actually, `client.get_item_path` exists.
    try:
         path_data = await client.get_item_path(account, root_item_id)
         # path_data is list of dicts: [{'id': 'root', 'name': 'Root'}, ...]
         # Construct path string
         # Onedrive root name is usually 'root', but path display usually starts after that?
         # Let's just join names.
         root_path = "/" + "/".join([p["name"] for p in path_data if p["name"] and p["name"].lower() != "root"])
         if root_path.endswith("/"):
             root_path = root_path[:-1] # avoid double slash
         if not root_path:
             root_path = "/"
    except Exception:
         root_path = f"/{root_item.name}"

    # Upsert root item
    await upsert_item_record(
        session,
        account_id=account.id,
        item_data=root_item,
        parent_id=None,
        path=root_path,
    )


    if root_item.item_type == "folder":
        await progress.set_total(None)
        await _update_metadata_recursive(
            client, 
            session, 
            account, 
            root_item.id, 
            category.id, 
            metadata_values_to_set, 
            stats,
            current_path=root_path,
            progress=progress,
            batch_id=batch_id,
        )
    else:
        # It's a single file
         await _update_single_item(
            session, 
            account.id, 
            root_item.id, 
            category.id, 
            metadata_values_to_set,
            batch_id=batch_id,
            job_id=progress.job_id,
        )
         stats["processed"] += 1
         stats["updated"] += 1
         await progress.set_total(1)
         await progress.increment()
         await progress.update_metrics(updated=stats["updated"], errors=stats["errors"])

    return stats


async def _update_metadata_recursive(
    client: DriveProviderClient,
    session: AsyncSession,
    account: LinkedAccount,
    folder_id: str,
    category_id: UUID,
    new_values: dict[str, Any],
    stats: dict,
    current_path: str,
    progress: JobProgressReporter,
    batch_id: uuid.UUID,
):
    """Recursively update metadata for all files in a folder."""
    
    # List items in folder
    try:
        children = await client.list_folder_items(account, folder_id)
    except Exception as e:
        logger.error(f"Failed to list folder {folder_id}: {e}")
        stats["errors"] += 1
        return

    items_to_process = children.items
    discovered = len(items_to_process)
    if discovered > 0:
        if progress.total is None:
            await progress.set_total(discovered)
        else:
            await progress.set_total(progress.total + discovered)
    
    while True:
        for item in items_to_process:
            item_path = f"{current_path}/{item.name}"
            # Upsert Item record
            await upsert_item_record(
                session,
                account_id=account.id,
                item_data=item,
                parent_id=folder_id,
                path=item_path,
            )

            if item.item_type == "folder":
                await _update_metadata_recursive(
                    client,
                    session,
                    account,
                    item.id,
                    category_id,
                    new_values,
                    stats,
                    current_path=item_path,
                    progress=progress,
                    batch_id=batch_id,
                )
            else:
                try:
                    await _update_single_item(
                        session,
                        account.id,
                        item.id,
                        category_id,
                        new_values,
                        batch_id=batch_id,
                        job_id=progress.job_id,
                    )
                    stats["updated"] += 1
                except Exception as e:
                    logger.error(f"Failed to update item {item.id}: {e}")
                    stats["errors"] += 1
                finally:
                    stats["processed"] += 1
                    if stats["processed"] % 10 == 0:
                        await progress.update_metrics(
                            updated=stats["updated"],
                            errors=stats["errors"],
                        )
                    await progress.increment()
        
        if children.next_link:
            try:
                children = await client.list_items_by_next_link(account, children.next_link)
                items_to_process = children.items
                discovered = len(items_to_process)
                if discovered > 0:
                    if progress.total is None:
                        await progress.set_total(discovered)
                    else:
                        await progress.set_total(progress.total + discovered)
            except Exception as e:
                logger.error(f"Failed to fetch next page for folder {folder_id}: {e}")
                break
        else:
            break


async def _update_single_item(
    session: AsyncSession,
    account_id: UUID,
    item_id: str,
    category_id: UUID,
    new_values: dict[str, Any],
    batch_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
):
    """Update or create metadata for a single item."""
    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    merged_values = dict(existing.values) if existing and existing.values else {}
    merged_values.update(new_values)

    await apply_metadata_change(
        session,
        account_id=account_id,
        item_id=item_id,
        category_id=category_id,
        values=merged_values,
        batch_id=batch_id,
        job_id=job_id,
    )


@register_handler("apply_metadata_recursive")
async def apply_metadata_recursive_handler(
    payload: dict, session: AsyncSession
) -> dict:
    """Apply metadata recursively to all items under a path prefix.

    Operates entirely on the local `items` table — no Graph API calls.

    Payload
    -------
    {
        "account_id": "uuid",
        "path_prefix": "/Comics/Marvel",
        "category_id": "uuid",
        "values": {"attr-uuid-1": "value1", "attr-uuid-2": "value2"},
        "include_folders": false
    }
    """
    account_id = UUID(payload["account_id"])
    path_prefix = payload["path_prefix"].rstrip("/")
    category_id = UUID(payload["category_id"])
    values = payload.get("values", {})
    include_folders = payload.get("include_folders", False)
    batch_id = UUID(payload.get("batch_id")) if payload.get("batch_id") else uuid.uuid4()
    progress = JobProgressReporter.from_payload(session, payload)

    query = select(Item).where(
        Item.account_id == account_id,
        Item.path.ilike(f"{path_prefix}/%"),
    )

    if not include_folders:
        query = query.where(Item.item_type == "file")

    result = await session.execute(query)
    items = result.scalars().all()

    stats = {
        "total": len(items),
        "created": 0,
        "updated": 0,
        "errors": 0,
        "batch_id": str(batch_id),
    }
    await progress.set_total(len(items))
    batch_count = 0

    for item in items:
        try:
            stmt = select(ItemMetadata).where(
                ItemMetadata.account_id == account_id,
                ItemMetadata.item_id == item.item_id,
            )
            meta_result = await session.execute(stmt)
            existing = meta_result.scalar_one_or_none()
            merged_values = dict(existing.values) if existing and existing.values else {}
            merged_values.update(values)

            changed = await apply_metadata_change(
                session,
                account_id=account_id,
                item_id=item.item_id,
                category_id=category_id,
                values=merged_values,
                batch_id=batch_id,
                job_id=progress.job_id,
            )

            if changed["changed"]:
                if existing:
                    stats["updated"] += 1
                else:
                    stats["created"] += 1

            batch_count += 1
            if batch_count >= 50:
                await session.commit()
                batch_count = 0

        except Exception as e:
            logger.error(f"Failed to apply metadata to item {item.item_id}: {e}")
            stats["errors"] += 1
        finally:
            await progress.increment()
            if progress.current % 10 == 0:
                await progress.update_metrics(
                    created=stats["created"],
                    updated=stats["updated"],
                    errors=stats["errors"],
                )

    if batch_count > 0:
        await session.commit()

    return stats


@register_handler("remove_metadata_recursive")
async def remove_metadata_recursive_handler(
    payload: dict, session: AsyncSession
) -> dict:
    """Remove metadata from a folder and all items under it.

    Payload
    -------
    {
        "account_id": "uuid",
        "path_prefix": "/Comics/Marvel"
    }
    """
    account_id = UUID(payload["account_id"])
    path_prefix = payload["path_prefix"].rstrip("/")
    batch_id = UUID(payload.get("batch_id")) if payload.get("batch_id") else uuid.uuid4()
    progress = JobProgressReporter.from_payload(session, payload)

    sub = select(Item.item_id).where(
        Item.account_id == account_id,
        or_(
            Item.path == path_prefix,
            Item.path.ilike(f"{path_prefix}/%"),
        ),
    ).scalar_subquery()

    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id.in_(sub),
    )
    result = await session.execute(stmt)
    metadata_list = result.scalars().all()

    deleted = 0
    await progress.set_total(len(metadata_list))
    for meta in metadata_list:
        changed = await apply_metadata_change(
            session,
            account_id=meta.account_id,
            item_id=meta.item_id,
            category_id=None,
            values=None,
            batch_id=batch_id,
            job_id=progress.job_id,
        )
        if changed["changed"]:
            deleted += 1
        await progress.increment()

    if deleted > 0:
        await session.commit()

    return {"deleted": deleted, "batch_id": str(batch_id)}

