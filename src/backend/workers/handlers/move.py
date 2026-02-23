"""Move items job handler."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import DriveOrganizerError
from backend.db.models import Item, LinkedAccount
from backend.services.item_index import (
    delete_item_and_descendants,
    parent_id_from_breadcrumb,
    path_from_breadcrumb,
    update_descendant_paths,
    upsert_item_record,
)
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager
from backend.workers.dispatcher import register_handler

logger = logging.getLogger(__name__)


@register_handler("move_items")
async def move_items_handler(payload: dict, session: AsyncSession) -> dict:
    """Handle move items job.

    Payload structure:
    {
        "source_account_id": "uuid",
        "source_item_id": "str",
        "destination_account_id": "uuid",
        "destination_folder_id": "str"
    }
    """
    source_account_id = UUID(payload["source_account_id"])
    destination_account_id = UUID(payload["destination_account_id"])
    source_item_id = payload["source_item_id"]
    destination_folder_id = payload.get("destination_folder_id", "root")

    # 1. Fetch accounts
    source_account = await session.get(LinkedAccount, source_account_id)
    dest_account = await session.get(LinkedAccount, destination_account_id)

    if not source_account or not dest_account:
        raise DriveOrganizerError("Source or destination account not found", status_code=404)

    token_manager = TokenManager(session)
    source_client = build_drive_client(source_account, token_manager)
    dest_client = build_drive_client(dest_account, token_manager)

    # 2. Check if accounts are the same
    if source_account_id == destination_account_id:
        logger.info(f"Moving item {source_item_id} within the same account {source_account_id}")
        old_path = await session.scalar(
            select(Item.path).where(
                Item.account_id == source_account_id,
                Item.item_id == source_item_id,
            )
        )
        moved_item = await source_client.update_item(
            source_account,
            source_item_id,
            parent_id=destination_folder_id,
        )
        breadcrumb = await source_client.get_item_path(source_account, moved_item.id)
        new_path = path_from_breadcrumb(breadcrumb)
        new_parent_id = parent_id_from_breadcrumb(breadcrumb)
        await upsert_item_record(
            session,
            account_id=source_account.id,
            item_data=moved_item,
            parent_id=new_parent_id,
            path=new_path,
        )
        if moved_item.item_type == "folder" and old_path and old_path != new_path:
            await update_descendant_paths(
                session,
                account_id=source_account.id,
                old_prefix=old_path,
                new_prefix=new_path,
            )
        await session.commit()
        return {"moved_item_id": moved_item.id, "method": "move"}

    # 3. different accounts -> Download and Upload
    logger.info(f"Moving item {source_item_id} across accounts {source_account_id} -> {destination_account_id}")

    # Get item metadata to know if it's a folder or file
    item = await source_client.get_item_metadata(source_account, source_item_id)

    if item.item_type == "folder":
        # Recursive move
        # For MVP, we might limit this or handle it recursively
        # Here is a simple implementation: Create folder on dest, then list children and move them
        # BUT: Doing this in one job might timeout.
        # Ideally, we should create a new job for each child or loop.
        # For now, let's implement a simple recursive function that runs within this job.
        await _move_folder_recursive(
            source_client,
            dest_client,
            source_account,
            dest_account,
            item,
            destination_folder_id,
        )
        await delete_item_and_descendants(
            session,
            account_id=source_account.id,
            item_id=source_item_id,
        )
        await session.commit()
        return {"moved_item_id": "folder_moved_recursively", "method": "copy_delete"}
    else:
        # It's a file
        new_id = await _move_single_file(
            source_client,
            dest_client,
            source_account,
            dest_account,
            item,
            destination_folder_id,
        )
        await delete_item_and_descendants(
            session,
            account_id=source_account.id,
            item_id=source_item_id,
        )
        if new_id:
            uploaded_item = await dest_client.get_item_metadata(dest_account, new_id)
            breadcrumb = await dest_client.get_item_path(dest_account, new_id)
            await upsert_item_record(
                session,
                account_id=dest_account.id,
                item_data=uploaded_item,
                parent_id=parent_id_from_breadcrumb(breadcrumb),
                path=path_from_breadcrumb(breadcrumb),
            )
        await session.commit()
        return {"moved_item_id": new_id, "method": "copy_delete"}


async def _move_single_file(
    source_client: DriveProviderClient,
    dest_client: DriveProviderClient,
    source_account: LinkedAccount,
    dest_account: LinkedAccount,
    item: Any,  # DriveItem
    dest_folder_id: str,
) -> str | None:
    """Download from source and upload to dest, then delete from source."""
    
    # 1. Download
    filename, content = await source_client.download_file_bytes(source_account, item.id)
    
    # 2. Upload
    # Check size for upload session? For now assume small files or use upload_small_file
    # which supports bytes. If content is large, we should use streaming, but 
    # DriveProviderClient.download_file_bytes loads into memory.
    # To improve, we should stream. But let's stick to what we have for MVP.
    
    # If size > 4MB, we should use upload session.
    # But download_file_bytes already loaded it in RAM.
    
    if item.size > 4 * 1024 * 1024:
        # Large file flow
        session_data = await dest_client.create_upload_session(dest_account, filename, dest_folder_id)
        upload_url = session_data["upload_url"]
        
        # Upload in chunks
        chunk_size = 327680 * 10  # ~3MB
        total_size = len(content) # We already have it in memory :( 
        
        upload_result: dict[str, Any] | None = None
        for i in range(0, total_size, chunk_size):
            chunk = content[i : i + chunk_size]
            upload_result = await dest_client.upload_chunk(
                upload_url,
                chunk,
                i,
                min(i + chunk_size, total_size) - 1,
                total_size
            )
        uploaded_item_id = upload_result.get("id") if isinstance(upload_result, dict) else None
    else:
        # Small file
        uploaded = await dest_client.upload_small_file(dest_account, filename, content, dest_folder_id)
        uploaded_item_id = uploaded.id

    # 3. Delete from source
    await source_client.delete_item(source_account, item.id)
    
    return uploaded_item_id


async def _move_folder_recursive(
    source_client: DriveProviderClient,
    dest_client: DriveProviderClient,
    source_account: LinkedAccount,
    dest_account: LinkedAccount,
    folder_item: Any,
    dest_parent_id: str,
):
    """Recursively move a folder."""
    # 1. Create folder on dest
    new_folder = await dest_client.create_folder(dest_account, folder_item.name, dest_parent_id)
    
    # 2. List children of source folder
    children = await source_client.list_folder_items(source_account, folder_item.id)
    
    # 3. Iteratively move children
    items_to_process = children.items
    
    # Handle pagination if many items
    while True:
        for child in items_to_process:
            if child.item_type == "folder":
                await _move_folder_recursive(
                    source_client,
                    dest_client,
                    source_account,
                    dest_account,
                    child,
                    new_folder.id,
                )
            else:
                await _move_single_file(
                    source_client,
                    dest_client,
                    source_account,
                    dest_account,
                    child,
                    new_folder.id,
                )
        
        if children.next_link:
            children = await source_client.list_items_by_next_link(source_account, children.next_link)
            items_to_process = children.items
        else:
            break

    # 4. Delete source folder (after all children moved)
    await source_client.delete_item(source_account, folder_item.id)
