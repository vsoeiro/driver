"""Application service for item metadata commands."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Item, ItemMetadata, LinkedAccount, MetadataCategory
from backend.schemas.metadata import ItemMetadataCreate
from backend.security.token_manager import TokenManager
from backend.services.metadata_versioning import apply_metadata_change, normalize_metadata_values
from backend.services.providers.factory import build_drive_client

logger = logging.getLogger(__name__)


class ItemMetadataCommandService:
    """Write-side service for metadata assignment/update flows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_item_metadata(self, metadata: ItemMetadataCreate) -> ItemMetadata:
        account = await self._session.get(LinkedAccount, metadata.account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        category = await self._session.get(MetadataCategory, metadata.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        if not category.is_active:
            raise HTTPException(status_code=400, detail="Category is inactive")

        await self._sync_item_record(account=account, item_id=metadata.item_id)

        existing_stmt = select(ItemMetadata).where(
            ItemMetadata.account_id == metadata.account_id,
            ItemMetadata.item_id == metadata.item_id,
        )
        existing = (await self._session.execute(existing_stmt)).scalar_one_or_none()

        normalized_values = normalize_metadata_values(metadata.values)
        if existing and existing.category_id == metadata.category_id:
            merged_values = normalize_metadata_values(existing.values)
            merged_values.update(normalized_values)
        else:
            merged_values = normalized_values

        await apply_metadata_change(
            self._session,
            account_id=metadata.account_id,
            item_id=metadata.item_id,
            category_id=metadata.category_id,
            values=merged_values,
        )
        await self._session.commit()

        query = select(ItemMetadata).where(
            ItemMetadata.account_id == metadata.account_id,
            ItemMetadata.item_id == metadata.item_id,
        )
        current = (await self._session.execute(query)).scalar_one_or_none()
        if not current:
            raise HTTPException(status_code=500, detail="Failed to save metadata")
        return current

    async def _sync_item_record(self, *, account: LinkedAccount, item_id: str) -> None:
        token_manager = TokenManager(self._session)
        client = build_drive_client(account, token_manager)
        try:
            drive_item = await client.get_item_metadata(account, item_id)
            stmt = select(Item).where(
                Item.account_id == account.id,
                Item.item_id == item_id,
            )
            db_item = (await self._session.execute(stmt)).scalar_one_or_none()

            extension = None
            if drive_item.item_type == "file" and "." in drive_item.name:
                extension = drive_item.name.rsplit(".", 1)[-1].lower()

            if db_item:
                db_item.name = drive_item.name
                db_item.size = drive_item.size
                db_item.modified_at = drive_item.modified_at
                db_item.last_synced_at = datetime.now(UTC)
                db_item.mime_type = drive_item.mime_type
                db_item.extension = extension
                return

            parent_id = None
            path_str = None
            try:
                path_data = await client.get_item_path(account, item_id)
                if len(path_data) >= 2:
                    parent_id = path_data[-2]["id"]
                path_names = [
                    p["name"]
                    for p in path_data
                    if p["name"] and p["name"].lower() != "root"
                ]
                path_str = "/" + "/".join(path_names) if path_names else "/"
            except Exception:
                pass

            db_item = Item(
                account_id=account.id,
                item_id=item_id,
                parent_id=parent_id,
                name=drive_item.name,
                path=path_str,
                item_type=drive_item.item_type,
                mime_type=drive_item.mime_type,
                extension=extension,
                size=drive_item.size,
                created_at=drive_item.created_at,
                modified_at=drive_item.modified_at,
                last_synced_at=datetime.now(UTC),
            )
            self._session.add(db_item)
        except Exception as exc:
            logger.error("Failed to sync Item record for %s: %s", item_id, exc)
