"""Metadata-focused repositories."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ItemMetadata


class ItemMetadataRepository:
    """Read helpers for item metadata used by routes and workers."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_items(
        self,
        *,
        account_id: UUID,
        item_ids: Sequence[str],
    ) -> dict[str, ItemMetadata]:
        if not item_ids:
            return {}
        stmt = select(ItemMetadata).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.item_id.in_(list(item_ids)),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return {row.item_id: row for row in rows}

    async def get_by_account_item_pairs(
        self,
        *,
        pairs: Sequence[tuple[UUID, str]],
    ) -> dict[tuple[UUID, str], ItemMetadata]:
        if not pairs:
            return {}
        conditions = [
            (ItemMetadata.account_id == account_id) & (ItemMetadata.item_id == item_id)
            for account_id, item_id in pairs
        ]
        stmt = select(ItemMetadata).where(or_(*conditions))
        rows = (await self._session.execute(stmt)).scalars().all()
        return {(row.account_id, row.item_id): row for row in rows}
