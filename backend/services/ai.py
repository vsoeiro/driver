"""Local AI services backed by configurable providers (Ollama MVP)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import MetadataCategory
from backend.schemas.ai import AICategorySuggestion
from backend.services.app_settings import AppSettingsService
from backend.services.metadata_versioning import apply_metadata_change


@dataclass(slots=True)
class AIInferenceConfig:
    provider: str
    base_url: str
    model: str
    temperature: float
    timeout_seconds: int
    enabled: bool


class OllamaClient:
    def __init__(self, config: AIInferenceConfig) -> None:
        self.config = config

    async def health(self) -> tuple[bool, str]:
        url = f"{self.config.base_url.rstrip('/')}/api/tags"
        timeout = httpx.Timeout(self.config.timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
            return True, "Ollama reachable"
        except Exception as exc:
            return False, str(exc)

    async def generate_json(self, prompt: str, system: str) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "format": "json",
            "options": {"temperature": self.config.temperature},
        }
        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        raw_response = data.get("response", "").strip()
        if not raw_response:
            raise ValueError("Model returned empty response")
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned invalid JSON: {raw_response[:300]}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Model JSON root must be an object")
        return parsed


class AIService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_config(self) -> AIInferenceConfig:
        settings = await AppSettingsService(self.session).get_runtime_settings()
        return AIInferenceConfig(
            provider=settings.ai_provider,
            base_url=settings.ai_base_url,
            model=settings.ai_model,
            temperature=settings.ai_temperature,
            timeout_seconds=settings.ai_timeout_seconds,
            enabled=settings.ai_enabled,
        )

    async def health(self) -> tuple[AIInferenceConfig, bool, str]:
        config = await self.get_config()
        if not config.enabled:
            return config, False, "AI is disabled by runtime settings"
        if config.provider != "ollama":
            return config, False, f"Provider '{config.provider}' not implemented yet"
        ok, detail = await OllamaClient(config).health()
        return config, ok, detail

    async def suggest_category_schema(
        self,
        *,
        document_type: str,
        sample_text: str | None,
    ) -> AICategorySuggestion:
        config = await self.get_config()
        if not config.enabled:
            raise ValueError("AI is disabled in runtime settings")
        if config.provider != "ollama":
            raise ValueError(f"Provider '{config.provider}' not implemented yet")

        system = (
            "You are an information architect for document metadata.\n"
            "Return only strict JSON object with keys: category_name, description, attributes.\n"
            "Each attribute must have: name, data_type (text|number|date|boolean|select), is_required, options.\n"
            "For non-select attributes set options=null.\n"
            "Do not include markdown or extra text."
        )
        prompt = (
            f"Document type: {document_type}\n"
            f"Sample text:\n{sample_text or '(none provided)'}\n\n"
            "Infer a practical metadata category schema with 4-10 attributes."
        )

        data = await OllamaClient(config).generate_json(prompt=prompt, system=system)
        return AICategorySuggestion.model_validate(data)

    async def extract_metadata_values(
        self,
        *,
        category_id: UUID,
        document_text: str,
        account_id: UUID | None = None,
        item_id: str | None = None,
        apply_to_item: bool = False,
    ) -> dict[str, Any]:
        config = await self.get_config()
        if not config.enabled:
            raise ValueError("AI is disabled in runtime settings")
        if config.provider != "ollama":
            raise ValueError(f"Provider '{config.provider}' not implemented yet")

        category = await self._get_category_with_attributes(category_id)
        attributes_payload = [
            {
                "id": str(attr.id),
                "name": attr.name,
                "data_type": attr.data_type,
                "is_required": attr.is_required,
                "options": attr.options,
            }
            for attr in category.attributes
        ]

        system = (
            "You extract metadata values from document text.\n"
            "Return strict JSON object with keys: values, confidence, notes.\n"
            "values must be an object where keys are attribute IDs exactly as provided.\n"
            "If unknown, omit key. Use ISO date (YYYY-MM-DD) for date fields."
        )
        prompt = (
            f"Category: {category.name}\n"
            f"Attributes JSON:\n{json.dumps(attributes_payload, ensure_ascii=True)}\n\n"
            f"Document text:\n{document_text}\n\n"
            "Extract best-effort values."
        )
        result = await OllamaClient(config).generate_json(prompt=prompt, system=system)
        values = result.get("values", {})
        if not isinstance(values, dict):
            raise ValueError("AI response 'values' must be an object")

        allowed_attr_ids = {str(attr.id) for attr in category.attributes}
        filtered_values = {k: v for k, v in values.items() if str(k) in allowed_attr_ids}

        output: dict[str, Any] = {
            "values": filtered_values,
            "confidence": result.get("confidence"),
            "notes": result.get("notes"),
            "applied": False,
            "metadata_id": None,
        }

        if apply_to_item:
            if account_id is None or not item_id:
                raise ValueError("account_id and item_id are required to apply metadata")
            change = await apply_metadata_change(
                self.session,
                account_id=account_id,
                item_id=item_id,
                category_id=category_id,
                values=filtered_values,
            )
            output["applied"] = bool(change.get("changed"))
            output["metadata_id"] = change.get("metadata_id")

        return output

    async def _get_category_with_attributes(self, category_id: UUID) -> MetadataCategory:
        stmt = (
            select(MetadataCategory)
            .where(MetadataCategory.id == category_id)
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()
        if not category:
            raise ValueError("Category not found")
        category.attributes.sort(key=lambda attr: attr.name.lower())
        return category
