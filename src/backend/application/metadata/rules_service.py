"""Application service for metadata rules lifecycle."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    LinkedAccount,
    MetadataAttribute,
    MetadataCategory,
    MetadataRule,
)
from backend.schemas.metadata import MetadataRuleCreate, MetadataRuleUpdate


class MetadataRulesService:
    """Encapsulate metadata rule CRUD and validation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_rules(self) -> list[MetadataRule]:
        stmt = select(MetadataRule).order_by(
            MetadataRule.priority.asc(), MetadataRule.created_at.asc()
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_rule(self, payload: MetadataRuleCreate) -> MetadataRule:
        category = await self._session.get(MetadataCategory, payload.target_category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        model_payload = payload.model_dump()
        validation_payload = payload.model_dump(mode="json")
        await self.validate_rule_configuration(validation_payload)
        model_payload["metadata_filters"] = validation_payload.get("metadata_filters", [])
        db_rule = MetadataRule(**model_payload)
        self._session.add(db_rule)
        await self._session.commit()
        await self._session.refresh(db_rule)
        return db_rule

    async def update_rule(
        self,
        *,
        rule_id: UUID,
        payload: MetadataRuleUpdate,
    ) -> MetadataRule:
        db_rule = await self._session.get(MetadataRule, rule_id)
        if not db_rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        updates = payload.model_dump(exclude_unset=True, mode="json")
        if "target_category_id" in updates:
            category = await self._session.get(
                MetadataCategory, updates["target_category_id"]
            )
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")

        for key, value in updates.items():
            setattr(db_rule, key, value)

        effective_payload = {
            "apply_metadata": db_rule.apply_metadata,
            "apply_remove_metadata": db_rule.apply_remove_metadata,
            "apply_rename": db_rule.apply_rename,
            "rename_template": db_rule.rename_template,
            "apply_move": db_rule.apply_move,
            "destination_account_id": db_rule.destination_account_id,
            "destination_folder_id": db_rule.destination_folder_id,
            "destination_path_template": db_rule.destination_path_template,
            "target_category_id": db_rule.target_category_id,
            "metadata_filters": db_rule.metadata_filters or [],
        }
        effective_payload.update({k: v for k, v in updates.items() if k in effective_payload})
        await self.validate_rule_configuration(effective_payload)

        await self._session.commit()
        await self._session.refresh(db_rule)
        return db_rule

    async def delete_rule(self, rule_id: UUID) -> None:
        db_rule = await self._session.get(MetadataRule, rule_id)
        if not db_rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        await self._session.delete(db_rule)
        await self._session.commit()

    async def validate_rule_configuration(self, payload: dict) -> None:
        if payload.get("apply_metadata", True) and payload.get("apply_remove_metadata"):
            raise HTTPException(
                status_code=400,
                detail="apply_metadata and apply_remove_metadata cannot both be true",
            )

        if payload.get("apply_rename") and not (payload.get("rename_template") or "").strip():
            raise HTTPException(
                status_code=400,
                detail="rename_template is required when apply_rename is true",
            )

        if payload.get("apply_move"):
            destination_folder_id = (payload.get("destination_folder_id") or "").strip()
            if not destination_folder_id:
                raise HTTPException(
                    status_code=400,
                    detail="destination_folder_id is required when apply_move is true",
                )

        if (
            not payload.get("apply_metadata", True)
            and not payload.get("apply_remove_metadata")
            and not payload.get("apply_rename")
            and not payload.get("apply_move")
        ):
            raise HTTPException(status_code=400, detail="At least one action must be enabled")

        destination_account_id = payload.get("destination_account_id")
        if destination_account_id:
            linked = await self._session.get(LinkedAccount, destination_account_id)
            if not linked:
                raise HTTPException(status_code=404, detail="Destination account not found")

        metadata_filters = payload.get("metadata_filters") or []
        if not isinstance(metadata_filters, list):
            raise HTTPException(status_code=400, detail="metadata_filters must be a list")
        if metadata_filters:
            target_category_id = payload.get("target_category_id")
            if not target_category_id:
                raise HTTPException(
                    status_code=400,
                    detail="target_category_id is required when metadata_filters are provided",
                )
            attr_ids = set(
                str(attr_id)
                for attr_id in (
                    await self._session.execute(
                        select(MetadataAttribute.id).where(
                            MetadataAttribute.category_id == target_category_id
                        )
                    )
                ).scalars()
            )
            allowed_operators = {
                "equals",
                "not_equals",
                "contains",
                "not_contains",
                "starts_with",
                "ends_with",
                "gt",
                "gte",
                "lt",
                "lte",
                "is_empty",
                "is_not_empty",
            }

            for index, rule_filter in enumerate(metadata_filters):
                if not isinstance(rule_filter, dict):
                    raise HTTPException(
                        status_code=400,
                        detail=f"metadata_filters[{index}] must be an object",
                    )
                source = str(rule_filter.get("source") or "metadata").strip().lower()
                if source not in {"metadata", "path"}:
                    raise HTTPException(
                        status_code=400,
                        detail=f"metadata_filters[{index}].source must be metadata or path",
                    )
                operator = str(rule_filter.get("operator") or "equals").strip().lower()
                if operator not in allowed_operators:
                    raise HTTPException(
                        status_code=400,
                        detail=f"metadata_filters[{index}].operator is invalid",
                    )
                if source == "metadata":
                    attr_id = str(rule_filter.get("attribute_id") or "").strip()
                    if not attr_id:
                        raise HTTPException(
                            status_code=400,
                            detail=f"metadata_filters[{index}].attribute_id is required for metadata filters",
                        )
                    if attr_id not in attr_ids:
                        raise HTTPException(
                            status_code=400,
                            detail=f"metadata_filters[{index}].attribute_id does not belong to target category",
                        )
