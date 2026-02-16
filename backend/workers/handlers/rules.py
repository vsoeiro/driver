"""Automatic metadata rule job handlers."""

from __future__ import annotations

import uuid
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Item, MetadataRule
from backend.services.metadata_versioning import apply_metadata_change
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter

logger = logging.getLogger(__name__)


def _build_rule_item_query(rule: MetadataRule):
    query = select(Item).where(Item.path.isnot(None))
    if rule.account_id:
        query = query.where(Item.account_id == rule.account_id)
    if rule.path_prefix:
        prefix = rule.path_prefix.rstrip("/")
        query = query.where(Item.path.ilike(f"{prefix}/%"))
    if rule.path_contains:
        query = query.where(Item.path.ilike(f"%{rule.path_contains}%"))
    if not rule.include_folders:
        query = query.where(Item.item_type == "file")
    return query.order_by(Item.path.asc())


@register_handler("apply_metadata_rule")
async def apply_metadata_rule_handler(payload: dict, session: AsyncSession) -> dict:
    """Apply a metadata rule to matching items."""
    rule_id = UUID(payload["rule_id"])
    batch_id = UUID(payload.get("batch_id")) if payload.get("batch_id") else uuid.uuid4()
    progress = JobProgressReporter.from_payload(session, payload)

    rule = await session.get(MetadataRule, rule_id)
    if not rule:
        raise ValueError(f"Rule {rule_id} not found")

    query = _build_rule_item_query(rule)
    result = await session.execute(query)
    items = result.scalars().all()

    await progress.set_total(len(items))

    stats = {"total": len(items), "changed": 0, "skipped": 0, "errors": 0, "batch_id": str(batch_id)}
    batch_count = 0

    for item in items:
        try:
            change = await apply_metadata_change(
                session,
                account_id=item.account_id,
                item_id=item.item_id,
                category_id=rule.target_category_id,
                values=rule.target_values,
                batch_id=batch_id,
                job_id=progress.job_id,
            )
            if change["changed"]:
                stats["changed"] += 1
            else:
                stats["skipped"] += 1
            batch_count += 1
            if batch_count >= 50:
                await session.commit()
                batch_count = 0
        except Exception as exc:
            logger.error("Rule %s failed for item %s: %s", rule_id, item.item_id, exc)
            stats["errors"] += 1
        finally:
            await progress.increment()
            if progress.current % 10 == 0:
                await progress.update_metrics(
                    changed=stats["changed"],
                    skipped=stats["skipped"],
                    errors=stats["errors"],
                )

    if batch_count > 0:
        await session.commit()

    return stats


@register_handler("undo_metadata_batch")
async def undo_metadata_batch_handler(payload: dict, session: AsyncSession) -> dict:
    """Undo metadata changes from an earlier batch id."""
    from backend.services.metadata_versioning import undo_metadata_batch

    batch_id = UUID(payload["batch_id"])
    progress = JobProgressReporter.from_payload(session, payload)
    # Undo iterates full batch; total is unknown before query inside service.
    await progress.set_total(None)
    result = await undo_metadata_batch(
        session,
        batch_id=batch_id,
        job_id=progress.job_id,
    )
    await progress.update_metrics(**result)
    return result
