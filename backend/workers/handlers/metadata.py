"""Metadata update job handler."""

import logging
from datetime import datetime, UTC
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Item, ItemMetadata, LinkedAccount, MetadataAttribute, MetadataCategory
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager
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
    stats = {"processed": 0, "updated": 0, "errors": 0}
    
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
    await upsert_item_record(session, account, root_item, parent_id=None, path=root_path)


    if root_item.item_type == "folder":
        await _update_metadata_recursive(
            client, 
            session, 
            account, 
            root_item.id, 
            category.id, 
            metadata_values_to_set, 
            stats,
            current_path=root_path
        )
    else:
        # It's a single file
         await _update_single_item(
            session, 
            account.id, 
            root_item.id, 
            category.id, 
            metadata_values_to_set
        )
         stats["processed"] += 1
         stats["updated"] += 1

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
    
    while True:
        for item in items_to_process:
            item_path = f"{current_path}/{item.name}"
            # Upsert Item record
            await upsert_item_record(session, account, item, parent_id=folder_id, path=item_path)

            if item.item_type == "folder":
                await _update_metadata_recursive(
                    client, session, account, item.id, category_id, new_values, stats, current_path=item_path
                )
            else:
                try:
                    await _update_single_item(
                        session, account.id, item.id, category_id, new_values
                    )
                    stats["updated"] += 1
                except Exception as e:
                    logger.error(f"Failed to update item {item.id}: {e}")
                    stats["errors"] += 1
                finally:
                    stats["processed"] += 1
        
        if children.next_link:
            try:
                children = await client.list_items_by_next_link(account, children.next_link)
                items_to_process = children.items
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
):
    """Update or create metadata for a single item."""
    # Check if metadata exists
    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id,
        ItemMetadata.category_id == category_id
    )
    result = await session.execute(stmt)
    item_metadata = result.scalar_one_or_none()

    if item_metadata:
        # Update existing
        # Merge new values with existing ones
        current_values = dict(item_metadata.values)
        current_values.update(new_values)
        item_metadata.values = current_values
    else:
        # Create new
        item_metadata = ItemMetadata(
            account_id=account_id,
            item_id=item_id,
            category_id=category_id,
            values=new_values
        )
        session.add(item_metadata)
    
    # Flush explicitly to detect errors early? 
    # Or rely on final commit in runner.
    # The runner commits at the end of the job. 
    # But if there are too many items, we might want to commit in batches?
    # For now, let's keep it simple. The runner transaction will handle it.
    # Only concern is memory if updating 10k items.


async def upsert_item_record(
    session: AsyncSession,
    account: LinkedAccount,
    item_data: Any, # DriveItem
    parent_id: str | None,
    path: str | None,
):
    """Upsert Item record."""
    stmt = select(Item).where(
        Item.account_id == account.id,
        Item.item_id == item_data.id
    )
    result = await session.execute(stmt)
    db_item = result.scalar_one_or_none()

    extension = None
    if item_data.item_type == "file" and "." in item_data.name:
        extension = item_data.name.rsplit(".", 1)[-1].lower()

    if db_item:
        db_item.name = item_data.name
        db_item.parent_id = parent_id
        db_item.path = path
        db_item.size = item_data.size
        db_item.modified_at = item_data.modified_at
        db_item.last_synced_at = datetime.now(UTC)
        db_item.mime_type = item_data.mime_type
        db_item.extension = extension
    else:
        db_item = Item(
            account_id=account.id,
            item_id=item_data.id,
            parent_id=parent_id,
            name=item_data.name,
            path=path,
            item_type=item_data.item_type,
            mime_type=item_data.mime_type,
            extension=extension,
            size=item_data.size,
            created_at=item_data.created_at,
            modified_at=item_data.modified_at,
            last_synced_at=datetime.now(UTC),
        )
        session.add(db_item)


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

    query = select(Item).where(
        Item.account_id == account_id,
        Item.path.ilike(f"{path_prefix}/%"),
    )

    if not include_folders:
        query = query.where(Item.item_type == "file")

    result = await session.execute(query)
    items = result.scalars().all()

    stats = {"total": len(items), "created": 0, "updated": 0, "errors": 0}
    batch_count = 0

    for item in items:
        try:
            stmt = select(ItemMetadata).where(
                ItemMetadata.account_id == account_id,
                ItemMetadata.item_id == item.item_id,
            )
            meta_result = await session.execute(stmt)
            existing = meta_result.scalar_one_or_none()

            if existing:
                if existing.category_id != category_id:
                    existing.category_id = category_id
                    existing.values = values
                else:
                    current = dict(existing.values)
                    current.update(values)
                    existing.values = current
                stats["updated"] += 1
            else:
                new_meta = ItemMetadata(
                    account_id=account_id,
                    item_id=item.item_id,
                    category_id=category_id,
                    values=values,
                )
                session.add(new_meta)
                stats["created"] += 1

            batch_count += 1
            if batch_count >= 50:
                await session.commit()
                batch_count = 0

        except Exception as e:
            logger.error(f"Failed to apply metadata to item {item.item_id}: {e}")
            stats["errors"] += 1

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
    for meta in metadata_list:
        await session.delete(meta)
        deleted += 1

    if deleted > 0:
        await session.commit()

    return {"deleted": deleted}

