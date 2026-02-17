"""Metadata versioning and undo helpers."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ItemMetadata, ItemMetadataHistory


def normalize_metadata_values(values: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize metadata values for stable comparisons/storage."""
    if not values:
        return {}
    normalized: dict[str, Any] = {}
    for key, value in values.items():
        normalized[str(key)] = value
    return normalized


def _snapshot(record: ItemMetadata | None) -> dict[str, Any]:
    if not record:
        return {
            "metadata_id": None,
            "category_id": None,
            "values": None,
            "version": None,
        }
    return {
        "metadata_id": record.id,
        "category_id": record.category_id,
        "values": normalize_metadata_values(record.values),
        "version": record.version,
    }


async def apply_metadata_change(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    item_id: str,
    category_id: uuid.UUID | None,
    values: dict[str, Any] | None = None,
    batch_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    action_override: str | None = None,
) -> dict[str, Any]:
    """Apply metadata change and record item history.

    If `category_id` is None, metadata is removed for the item.
    """
    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    previous = _snapshot(existing)

    normalized_values = normalize_metadata_values(values)

    if category_id is None:
        if not existing:
            return {"changed": False, "action": "NOOP", "metadata_id": None}

        metadata_id = existing.id
        await session.delete(existing)
        await session.flush()
        new_snapshot = {"metadata_id": None, "category_id": None, "values": None, "version": None}
        history_action = action_override or "DELETE"
    else:
        if existing:
            same_category = existing.category_id == category_id
            same_values = normalize_metadata_values(existing.values) == normalized_values
            if same_category and same_values:
                return {"changed": False, "action": "NOOP", "metadata_id": existing.id}

            existing.category_id = category_id
            existing.values = normalized_values
            existing.version = (existing.version or 0) + 1
            await session.flush()
            metadata_id = existing.id
            new_snapshot = _snapshot(existing)
            history_action = action_override or "UPDATE"
        else:
            created = ItemMetadata(
                account_id=account_id,
                item_id=item_id,
                category_id=category_id,
                values=normalized_values,
                version=1,
            )
            session.add(created)
            await session.flush()
            metadata_id = created.id
            new_snapshot = _snapshot(created)
            history_action = action_override or "CREATE"

    history = ItemMetadataHistory(
        # Keep a metadata FK reference only when the row exists after the change.
        # This avoids FK violations for DELETE/UNDO-delete operations.
        metadata_id=new_snapshot["metadata_id"],
        account_id=account_id,
        item_id=item_id,
        action=history_action,
        previous_category_id=previous["category_id"],
        previous_values=previous["values"],
        previous_version=previous["version"],
        new_category_id=new_snapshot["category_id"],
        new_values=new_snapshot["values"],
        new_version=new_snapshot["version"],
        batch_id=batch_id,
        job_id=job_id,
    )
    session.add(history)
    await session.flush()

    return {
        "changed": True,
        "action": history_action,
        "metadata_id": metadata_id,
        "history_id": history.id,
    }


async def undo_metadata_batch(
    session: AsyncSession,
    *,
    batch_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Undo all metadata changes from a batch."""
    stmt = (
        select(ItemMetadataHistory)
        .where(ItemMetadataHistory.batch_id == batch_id)
        .order_by(ItemMetadataHistory.created_at.desc())
    )
    result = await session.execute(stmt)
    history_rows = result.scalars().all()

    restored = 0
    skipped = 0

    for row in history_rows:
        change = await apply_metadata_change(
            session,
            account_id=row.account_id,
            item_id=row.item_id,
            category_id=row.previous_category_id,
            values=row.previous_values,
            batch_id=None,
            job_id=job_id,
            action_override="UNDO",
        )
        if change["changed"]:
            restored += 1
        else:
            skipped += 1

    return {"restored": restored, "skipped": skipped}
