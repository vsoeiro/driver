"""Helpers to keep the local items index consistent with provider operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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


def build_item_signature(
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
    """Public helper for signature comparisons in bulk reconcile flows."""
    return _item_signature(
        parent_id=parent_id,
        path=path,
        name=name,
        item_type=item_type,
        size=size,
        modified_at=modified_at,
        mime_type=mime_type,
        extension=extension,
    )


def build_item_payload(
    *,
    account_id: UUID,
    item_data: Any,
    parent_id: str | None,
    path: str | None,
    last_synced_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a normalized Item payload used by bulk upsert paths."""
    extension = _compute_extension(item_data)
    synced_at = last_synced_at or datetime.now(UTC)
    return {
        "account_id": account_id,
        "item_id": item_data.id,
        "parent_id": parent_id,
        "name": item_data.name,
        "path": path,
        "item_type": item_data.item_type,
        "mime_type": item_data.mime_type,
        "extension": extension,
        "size": item_data.size,
        "created_at": item_data.created_at,
        "modified_at": item_data.modified_at,
        "last_synced_at": synced_at,
    }


def build_item_signature_from_payload(payload: dict[str, Any]) -> tuple[Any, ...]:
    """Create a compare signature from a normalized item payload."""
    return _item_signature(
        parent_id=payload.get("parent_id"),
        path=payload.get("path"),
        name=str(payload.get("name") or ""),
        item_type=str(payload.get("item_type") or "file"),
        size=int(payload.get("size") or 0),
        modified_at=payload.get("modified_at"),
        mime_type=payload.get("mime_type"),
        extension=payload.get("extension"),
    )


def build_item_signature_from_db_row(
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
    """Create a compare signature from a row returned by DB queries."""
    return _item_signature(
        parent_id=parent_id,
        path=path,
        name=name,
        item_type=item_type,
        size=size,
        modified_at=modified_at,
        mime_type=mime_type,
        extension=extension,
    )


async def fetch_item_signatures_by_item_id(
    session: AsyncSession,
    *,
    account_id: UUID,
) -> dict[str, tuple[Any, ...]]:
    """Fetch signatures for all indexed items of an account."""
    stmt = select(
        Item.item_id,
        Item.parent_id,
        Item.path,
        Item.name,
        Item.item_type,
        Item.size,
        Item.modified_at,
        Item.mime_type,
        Item.extension,
    ).where(Item.account_id == account_id)
    rows = (await session.execute(stmt)).all()
    signatures: dict[str, tuple[Any, ...]] = {}
    for (
        item_id,
        parent_id,
        path,
        name,
        item_type,
        size,
        modified_at,
        mime_type,
        extension,
    ) in rows:
        signatures[str(item_id)] = build_item_signature_from_db_row(
            parent_id=parent_id,
            path=path,
            name=name,
            item_type=item_type,
            size=size,
            modified_at=modified_at,
            mime_type=mime_type,
            extension=extension,
        )
    return signatures


async def bulk_upsert_item_payloads(
    session: AsyncSession,
    *,
    payloads: Sequence[dict[str, Any]],
    chunk_size: int = 500,
) -> None:
    """Bulk upsert item payloads using native conflict handling per dialect."""
    if not payloads:
        return

    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""

    updatable_columns = {
        "parent_id",
        "name",
        "path",
        "item_type",
        "mime_type",
        "extension",
        "size",
        "modified_at",
        "last_synced_at",
    }

    for i in range(0, len(payloads), chunk_size):
        chunk = list(payloads[i : i + chunk_size])
        if dialect_name == "postgresql":
            stmt = pg_insert(Item).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Item.account_id, Item.item_id],
                set_={column: getattr(stmt.excluded, column) for column in updatable_columns},
            )
            await session.execute(stmt)
            continue

        if dialect_name == "sqlite":
            stmt = sqlite_insert(Item).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["account_id", "item_id"],
                set_={column: getattr(stmt.excluded, column) for column in updatable_columns},
            )
            await session.execute(stmt)
            continue

        # Fallback for unexpected dialects.
        for payload in chunk:
            updated = await session.execute(
                update(Item)
                .where(
                    Item.account_id == payload["account_id"],
                    Item.item_id == payload["item_id"],
                )
                .values(**{column: payload.get(column) for column in updatable_columns})
            )
            if int(updated.rowcount or 0) == 0:
                session.add(Item(**payload))


async def upsert_item_record(
    session: AsyncSession,
    *,
    account_id: UUID,
    item_data: Any,
    parent_id: str | None,
    path: str | None,
) -> str:
    """Upsert one item record and return created/updated/unchanged."""
    payload = build_item_payload(
        account_id=account_id,
        item_data=item_data,
        parent_id=parent_id,
        path=path,
    )
    result = await session.execute(
        select(Item).where(
            Item.account_id == account_id,
            Item.item_id == payload["item_id"],
        )
    )
    db_item = result.scalar_one_or_none()

    new_sig = build_item_signature_from_payload(payload)

    if db_item is None:
        session.add(Item(**payload))
        return "created"

    old_sig = build_item_signature(
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

    db_item.name = payload["name"]
    db_item.parent_id = payload["parent_id"]
    db_item.path = payload["path"]
    db_item.item_type = payload["item_type"]
    db_item.size = payload["size"]
    db_item.modified_at = payload["modified_at"]
    db_item.last_synced_at = payload["last_synced_at"]
    db_item.mime_type = payload["mime_type"]
    db_item.extension = payload["extension"]
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
