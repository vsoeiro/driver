"""Move items job handler."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.drive.transfer_service import DriveTransferService
from backend.core.exceptions import DriveOrganizerError
from backend.db.models import Item, LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.item_index import (
    delete_item_and_descendants,
    parent_id_from_breadcrumb,
    path_from_breadcrumb,
    update_descendant_paths,
    upsert_item_record,
)
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
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
        raise DriveOrganizerError(
            "Source or destination account not found", status_code=404
        )

    token_manager = TokenManager(session)
    source_client = build_drive_client(source_account, token_manager)
    dest_client = build_drive_client(dest_account, token_manager)
    transfer_service = DriveTransferService()

    # 2. Check if accounts are the same
    if source_account_id == destination_account_id:
        logger.info(
            f"Moving item {source_item_id} within the same account {source_account_id}"
        )
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
    logger.info(
        f"Moving item {source_item_id} across accounts {source_account_id} -> {destination_account_id}"
    )

    # Get item metadata to know if it's a folder or file
    item = await source_client.get_item_metadata(source_account, source_item_id)

    if item.item_type == "folder":
        await _move_folder_recursive(
            source_client,
            dest_client,
            source_account,
            dest_account,
            item,
            destination_folder_id,
            transfer_service=transfer_service,
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
        new_id = await transfer_service.transfer_file_between_accounts(
            source_client=source_client,
            destination_client=dest_client,
            source_account=source_account,
            destination_account=dest_account,
            source_item_id=item.id,
            source_item_name=item.name,
            destination_folder_id=destination_folder_id,
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


async def _move_folder_recursive(
    source_client: DriveProviderClient,
    dest_client: DriveProviderClient,
    source_account: LinkedAccount,
    dest_account: LinkedAccount,
    folder_item: Any,
    dest_parent_id: str,
    transfer_service: DriveTransferService,
):
    """Recursively move a folder."""
    # 1. Create folder on dest
    new_folder = await dest_client.create_folder(
        dest_account, folder_item.name, dest_parent_id
    )

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
                    transfer_service=transfer_service,
                )
            else:
                await transfer_service.transfer_file_between_accounts(
                    source_client=source_client,
                    destination_client=dest_client,
                    source_account=source_account,
                    destination_account=dest_account,
                    source_item_id=child.id,
                    source_item_name=child.name,
                    destination_folder_id=new_folder.id,
                )

        if children.next_link:
            children = await source_client.list_items_by_next_link(
                source_account, children.next_link
            )
            items_to_process = children.items
        else:
            break

    # 4. Delete source folder (after all children moved)
    await source_client.delete_item(source_account, folder_item.id)
