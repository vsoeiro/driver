"""Metadata-focused repositories."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ItemMetadata

_MAX_QUERY_ARGS = 32767
_ARGS_PER_ACCOUNT_ITEM_PAIR = 2
# Larger tuple-IN batches started tripping asyncpg/Postgres stack depth limits.
_MAX_PAIRS_PER_BATCH = 2000


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

        max_pairs_per_batch = min(
            _MAX_PAIRS_PER_BATCH,
            _MAX_QUERY_ARGS // _ARGS_PER_ACCOUNT_ITEM_PAIR,
        )
        result: dict[tuple[UUID, str], ItemMetadata] = {}

        for idx in range(0, len(pairs), max_pairs_per_batch):
            batch = pairs[idx : idx + max_pairs_per_batch]
            stmt = select(ItemMetadata).where(
                tuple_(ItemMetadata.account_id, ItemMetadata.item_id).in_(list(batch))
            )
            rows = (await self._session.execute(stmt)).scalars().all()
            for row in rows:
                result[(row.account_id, row.item_id)] = row

        return result
