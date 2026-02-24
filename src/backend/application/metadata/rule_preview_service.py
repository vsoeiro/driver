"""Application service for metadata rule preview."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.metadata.repositories import ItemMetadataRepository
from backend.db.models import Item
from backend.schemas.metadata import (
    MetadataRulePreviewRequest,
    MetadataRulePreviewResponse,
)
from backend.services.metadata_versioning import normalize_metadata_values


class RulePreviewService:
    """Compute preview stats for a metadata rule without side effects."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._metadata_repo = ItemMetadataRepository(session)

    async def preview(
        self,
        request: MetadataRulePreviewRequest,
    ) -> MetadataRulePreviewResponse:
        query = select(Item).where(Item.path.isnot(None))
        if request.account_id:
            query = query.where(Item.account_id == request.account_id)
        if request.path_prefix:
            prefix = request.path_prefix.rstrip("/")
            query = query.where(Item.path.ilike(f"{prefix}/%"))
        if request.path_contains:
            query = query.where(Item.path.ilike(f"%{request.path_contains}%"))
        if not request.include_folders:
            query = query.where(Item.item_type == "file")

        items = (await self._session.execute(query)).scalars().all()
        lookup_pairs = [(item.account_id, item.item_id) for item in items]
        metadata_by_pair = await self._metadata_repo.get_by_account_item_pairs(
            pairs=lookup_pairs
        )

        target_values = normalize_metadata_values(request.target_values)
        to_change = 0
        already_compliant = 0
        sample_item_ids: list[str] = []
        has_organize_actions = request.apply_rename or request.apply_move

        for item in items:
            current = metadata_by_pair.get((item.account_id, item.item_id))
            current_values = normalize_metadata_values(current.values) if current else {}
            same_metadata = (
                current is not None
                and current.category_id == request.target_category_id
                and current_values == target_values
            )
            same = same_metadata and not has_organize_actions
            if same:
                already_compliant += 1
            else:
                to_change += 1
                if len(sample_item_ids) < max(1, request.limit):
                    sample_item_ids.append(item.item_id)

        return MetadataRulePreviewResponse(
            total_matches=len(items),
            to_change=to_change,
            already_compliant=already_compliant,
            sample_item_ids=sample_item_ids,
        )
