"""Application service for metadata rules lifecycle."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LinkedAccount, MetadataCategory, MetadataRule
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
        await self.validate_rule_configuration(model_payload)
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

        updates = payload.model_dump(exclude_unset=True)
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
            "apply_rename": db_rule.apply_rename,
            "rename_template": db_rule.rename_template,
            "apply_move": db_rule.apply_move,
            "destination_account_id": db_rule.destination_account_id,
            "destination_folder_id": db_rule.destination_folder_id,
            "destination_path_template": db_rule.destination_path_template,
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
            and not payload.get("apply_rename")
            and not payload.get("apply_move")
        ):
            raise HTTPException(status_code=400, detail="At least one action must be enabled")

        destination_account_id = payload.get("destination_account_id")
        if destination_account_id:
            linked = await self._session.get(LinkedAccount, destination_account_id)
            if not linked:
                raise HTTPException(status_code=404, detail="Destination account not found")
