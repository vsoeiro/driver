"""Helpers to keep the local items index consistent with provider operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Item


def build_item_path(parent_path: str | None, name: str) -> str:
    """Build a full item path using a parent path and child name."""
    if not parent_path or parent_path == "/":
        return f"/{name}"
    return f"{parent_path.rstrip('/')}/{name}"


def path_from_breadcrumb(breadcrumb: list[dict[str, Any]]) -> str:
    """Convert provider breadcrumb payload to canonical '/A/B/C' path."""
    names = [part.get("name") for part in breadcrumb if part.get("name")]
    filtered = [name for name in names if str(name).lower() != "root"]
    if not filtered:
        return "/"
    return "/" + "/".join(filtered)


def parent_id_from_breadcrumb(breadcrumb: list[dict[str, Any]]) -> str | None:
    """Extract parent ID from breadcrumb chain."""
    if len(breadcrumb) < 2:
        return None
    return breadcrumb[-2].get("id")


def _compute_extension(item_data: Any) -> str | None:
    if item_data.item_type != "file" or "." not in item_data.name:
        return None
    return item_data.name.rsplit(".", 1)[-1].lower()


def _item_signature(
    *,
    parent_id: str | None,
    path: str | None,
    name: str,
    item_type: str,
    size: int,
    modified_at: datetime | None,
    mime_type: str | None,
    extension: str | None,
) -> tuple[Any, ...]:
    return (
        parent_id,
        path,
        name,
        item_type,
        size,
        modified_at,
        mime_type,
        extension,
    )


async def upsert_item_record(
    session: AsyncSession,
    *,
    account_id: UUID,
    item_data: Any,
    parent_id: str | None,
    path: str | None,
) -> str:
    """Upsert one item record and return created/updated/unchanged."""
    result = await session.execute(
        select(Item).where(
            Item.account_id == account_id,
            Item.item_id == item_data.id,
        )
    )
    db_item = result.scalar_one_or_none()

    extension = _compute_extension(item_data)
    new_sig = _item_signature(
        parent_id=parent_id,
        path=path,
        name=item_data.name,
        item_type=item_data.item_type,
        size=item_data.size,
        modified_at=item_data.modified_at,
        mime_type=item_data.mime_type,
        extension=extension,
    )

    if db_item is None:
        session.add(
            Item(
                account_id=account_id,
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
        )
        return "created"

    old_sig = _item_signature(
        parent_id=db_item.parent_id,
        path=db_item.path,
        name=db_item.name,
        item_type=db_item.item_type,
        size=db_item.size,
        modified_at=db_item.modified_at,
        mime_type=db_item.mime_type,
        extension=db_item.extension,
    )
    if old_sig == new_sig:
        return "unchanged"

    db_item.name = item_data.name
    db_item.parent_id = parent_id
    db_item.path = path
    db_item.item_type = item_data.item_type
    db_item.size = item_data.size
    db_item.modified_at = item_data.modified_at
    db_item.last_synced_at = datetime.now(UTC)
    db_item.mime_type = item_data.mime_type
    db_item.extension = extension
    return "updated"


async def get_item_path(session: AsyncSession, *, account_id: UUID, item_id: str) -> str | None:
    """Return indexed path for an item id."""
    return await session.scalar(
        select(Item.path).where(
            Item.account_id == account_id,
            Item.item_id == item_id,
        )
    )


async def delete_item_and_descendants(
    session: AsyncSession,
    *,
    account_id: UUID,
    item_id: str,
) -> int:
    """Delete one item and descendants based on indexed path."""
    item_path = await get_item_path(session, account_id=account_id, item_id=item_id)

    if item_path:
        stmt = delete(Item).where(
            Item.account_id == account_id,
            or_(Item.path == item_path, Item.path.like(f"{item_path}/%")),
        )
    else:
        stmt = delete(Item).where(
            Item.account_id == account_id,
            Item.item_id == item_id,
        )

    result = await session.execute(stmt)
    return int(result.rowcount or 0)


async def delete_items_by_ids(
    session: AsyncSession,
    *,
    account_id: UUID,
    item_ids: list[str],
    chunk_size: int = 500,
) -> int:
    """Delete multiple items by id in chunks."""
    if not item_ids:
        return 0

    deleted_total = 0
    for i in range(0, len(item_ids), chunk_size):
        chunk = item_ids[i : i + chunk_size]
        result = await session.execute(
            delete(Item).where(
                Item.account_id == account_id,
                Item.item_id.in_(chunk),
            )
        )
        deleted_total += int(result.rowcount or 0)
    return deleted_total


async def update_descendant_paths(
    session: AsyncSession,
    *,
    account_id: UUID,
    old_prefix: str,
    new_prefix: str,
) -> int:
    """Rewrite descendant paths when a folder is renamed or moved."""
    if not old_prefix or not new_prefix or old_prefix == new_prefix:
        return 0

    result = await session.execute(
        update(Item)
        .where(
            Item.account_id == account_id,
            Item.path.like(f"{old_prefix}/%"),
        )
        .values(path=func.replace(Item.path, old_prefix, new_prefix))
    )
    return int(result.rowcount or 0)
