"""Sync items job handler."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LinkedAccount
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager
from backend.workers.dispatcher import register_handler
from backend.workers.handlers.metadata import upsert_item_record

logger = logging.getLogger(__name__)


class SyncContext:
    """Context for sync operation to handle batch commits."""
    def __init__(self, session: AsyncSession, batch_size: int = 50):
        self.session = session
        self.batch_size = batch_size
        self.stats = {"processed": 0, "created": 0, "updated": 0, "errors": 0}
        self.pending_commits = 0

    async def increment_and_commit(self):
        """Increment processed count and commit if batch size reached."""
        self.stats["processed"] += 1
        self.pending_commits += 1
        if self.pending_commits >= self.batch_size:
            try:
                await self.session.commit()
                # Yield control after commit to be nice to other tasks
                await asyncio.sleep(0.01)
                self.pending_commits = 0
            except Exception as e:
                logger.error(f"Failed to commit batch: {e}")
                raise


@register_handler("sync_items")
async def sync_items_handler(payload: dict, session: AsyncSession) -> dict:
    """Handle sync items job.

    Payload structure:
    {
        "account_id": "uuid"
    }
    """
    account_id = UUID(payload["account_id"])

    # 1. Fetch account
    account = await session.get(LinkedAccount, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    token_manager = TokenManager(session)
    client = build_drive_client(account, token_manager)

    # Use context for stats and batch commit
    ctx = SyncContext(session, batch_size=50)

    # 2. Get root item
    try:
        root_item = await client.get_item_metadata(account, "root")
        
        # Resolve root path
        root_path = "/"
        
        await upsert_item_record(session, account, root_item, parent_id=None, path=root_path)
        await ctx.increment_and_commit()
        
        # 3. Recursive sync
        await _sync_folder_recursive(
            client,
            ctx,
            account,
            root_item.id,
            root_path
        )
        
        # Final commit to ensure remaining items are saved
        if ctx.pending_commits > 0:
            await session.commit()

    except Exception as e:
        logger.error(f"Sync job failed for account {account_id}: {e}")
        raise

    return ctx.stats


async def _sync_folder_recursive(
    client: DriveProviderClient,
    ctx: SyncContext,
    account: LinkedAccount,
    folder_id: str,
    current_path: str,
):
    """Recursively sync folder items."""
    
    try:
        children = await client.list_folder_items(account, folder_id)
    except Exception as e:
        logger.error(f"Failed to list folder {folder_id}: {e}")
        ctx.stats["errors"] += 1
        return

    items_to_process = children.items
    
    while True:
        for item in items_to_process:
            try:
                item_path = f"{current_path}/{item.name}"
                if current_path == "/": # handle root case to avoid //
                     item_path = f"/{item.name}"
                     
                await upsert_item_record(ctx.session, account, item, parent_id=folder_id, path=item_path)
                await ctx.increment_and_commit()
                
                if item.item_type == "folder":
                    await _sync_folder_recursive(
                        client, ctx, account, item.id, item_path
                    )
            except Exception as e:
                logger.error(f"Failed to sync item {item.id}: {e}")
                ctx.stats["errors"] += 1

        if children.next_link:
            try:
                children = await client.list_items_by_next_link(account, children.next_link)
                items_to_process = children.items
            except Exception as e:
                logger.error(f"Failed to fetch next page for folder {folder_id}: {e}")
                break
        else:
            break
