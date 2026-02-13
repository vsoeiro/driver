"""Move items job handler."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import DriveOrganizerError
from backend.db.models import LinkedAccount
from backend.services.graph_client import GraphClient
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
    client = GraphClient(token_manager)

    # 2. Check if accounts are the same
    if source_account_id == destination_account_id:
        logger.info(f"Moving item {source_item_id} within the same account {source_account_id}")
        moved_item = await client.update_item(
            source_account,
            source_item_id,
            parent_id=destination_folder_id,
        )
        return {"moved_item_id": moved_item.id, "method": "move"}

    # 3. different accounts -> Download and Upload
    logger.info(f"Moving item {source_item_id} across accounts {source_account_id} -> {destination_account_id}")

    # Get item metadata to know if it's a folder or file
    item = await client.get_item_metadata(source_account, source_item_id)

    if item.item_type == "folder":
        # Recursive move
        # For MVP, we might limit this or handle it recursively
        # Here is a simple implementation: Create folder on dest, then list children and move them
        # BUT: Doing this in one job might timeout.
        # Ideally, we should create a new job for each child or loop.
        # For now, let's implement a simple recursive function that runs within this job.
        await _move_folder_recursive(client, source_account, dest_account, item, destination_folder_id)
        return {"moved_item_id": "folder_moved_recursively", "method": "copy_delete"}
    else:
        # It's a file
        new_id = await _move_single_file(client, source_account, dest_account, item, destination_folder_id)
        return {"moved_item_id": new_id, "method": "copy_delete"}


async def _move_single_file(
    client: GraphClient,
    source_account: LinkedAccount,
    dest_account: LinkedAccount,
    item: Any,  # DriveItem
    dest_folder_id: str,
) -> str:
    """Download from source and upload to dest, then delete from source."""
    
    # 1. Download
    filename, content = await client.download_file_bytes(source_account, item.id)
    
    # 2. Upload
    # Check size for upload session? For now assume small files or use upload_small_file
    # which supports bytes. If content is large, we should use streaming, but 
    # GraphClient.download_file_bytes loads into memory.
    # To improve, we should stream. But let's stick to what we have for MVP.
    
    # If size > 4MB, we should use upload session.
    # But download_file_bytes already loaded it in RAM.
    
    if item.size > 4 * 1024 * 1024:
        # Large file flow
        session_data = await client.create_upload_session(dest_account, filename, dest_folder_id)
        upload_url = session_data["upload_url"]
        
        # Upload in chunks
        chunk_size = 327680 * 10  # ~3MB
        total_size = len(content) # We already have it in memory :( 
        
        for i in range(0, total_size, chunk_size):
            chunk = content[i : i + chunk_size]
            await client.upload_chunk(
                upload_url,
                chunk,
                i,
                min(i + chunk_size, total_size) - 1,
                total_size
            )
        # Verify? Graph API completes automatically.
        # We don't get the item ID back easily from the chunk upload unless it returns it on last chunk.
        # Assuming success if no error.
    else:
        # Small file
        await client.upload_small_file(dest_account, filename, content, dest_folder_id)

    # 3. Delete from source
    await client.delete_item(source_account, item.id)
    
    return "moved"


async def _move_folder_recursive(
    client: GraphClient,
    source_account: LinkedAccount,
    dest_account: LinkedAccount,
    folder_item: Any,
    dest_parent_id: str,
):
    """Recursively move a folder."""
    # 1. Create folder on dest
    new_folder = await client.create_folder(dest_account, folder_item.name, dest_parent_id)
    
    # 2. List children of source folder
    children = await client.list_folder_items(source_account, folder_item.id)
    
    # 3. Iteratively move children
    items_to_process = children.items
    
    # Handle pagination if many items
    while True:
        for child in items_to_process:
            if child.item_type == "folder":
                await _move_folder_recursive(client, source_account, dest_account, child, new_folder.id)
            else:
                await _move_single_file(client, source_account, dest_account, child, new_folder.id)
        
        if children.next_link:
            children = await client.list_items_by_next_link(source_account, children.next_link)
            items_to_process = children.items
        else:
            break

    # 4. Delete source folder (after all children moved)
    await client.delete_item(source_account, folder_item.id)
