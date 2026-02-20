"""Local AI services backed by configurable providers (Ollama MVP)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from dataclasses import dataclass
import logging
import io
from typing import Any
from uuid import UUID

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import LinkedAccount, MetadataCategory
from backend.schemas.ai import AICategorySuggestion
from backend.services.app_settings import AppSettingsService
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager

logger = logging.getLogger(__name__)
COMIC_AI_ALLOWED_FIELD_KEYS = {
    "series",
    "volume",
    "issue_number",
    "title",
    "publisher",
    "writer",
    "penciller",
}


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

    async def ensure_model_available(self) -> bool:
        """Ensure configured model exists locally in Ollama.

        Returns True when the model had to be pulled automatically.
        """
        base_url = self.config.base_url.rstrip("/")
        tags_url = f"{base_url}/api/tags"
        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(tags_url)
            response.raise_for_status()
            try:
                payload = response.json() or {}
            except Exception:
                payload = {}

        if self._model_present_in_tags(payload, self.config.model):
            return False

        logger.warning(
            "Ollama model '%s' not found locally. Starting automatic pull.",
            self.config.model,
        )
        pull_timeout = httpx.Timeout(max(self.config.timeout_seconds, 3600))
        pull_url = f"{base_url}/api/pull"
        async with httpx.AsyncClient(timeout=pull_timeout) as client:
            response = await client.post(
                pull_url,
                json={"name": self.config.model, "stream": False},
            )
            if response.status_code >= 400:
                detail = response.text.strip()
                raise ValueError(
                    f"Failed to auto-pull Ollama model '{self.config.model}': HTTP {response.status_code} {detail}"
                )

        logger.info("Ollama model '%s' pulled successfully.", self.config.model)
        return True

    @staticmethod
    def _model_present_in_tags(tags_payload: dict[str, Any], target_model: str) -> bool:
        models = tags_payload.get("models") or []
        target = (target_model or "").strip().lower()
        if not target:
            return False

        for model in models:
            if not isinstance(model, dict):
                continue
            name = str(model.get("name") or "").strip().lower()
            if not name:
                continue
            if name == target:
                return True
            # Accept default tag resolution if user set base name without :tag.
            if ":" not in target and name.startswith(f"{target}:"):
                return True
        return False

    async def generate_json(self, prompt: str, system: str) -> dict[str, Any]:
        await self.ensure_model_available()
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

    async def generate_json_with_images(
        self,
        *,
        user_content: str,
        system: str,
        images: list[bytes] | None = None,
    ) -> dict[str, Any]:
        await self.ensure_model_available()
        base_url = self.config.base_url.rstrip("/")
        chat_url = f"{base_url}/api/chat"
        encoded_images = []
        for image in images or []:
            if image:
                normalized = self._normalize_image_for_ollama(image)
                encoded_images.append(base64.b64encode(normalized).decode("ascii"))

        chat_payload = {
            "model": self.config.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": self.config.temperature},
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": user_content,
                    "images": encoded_images,
                },
            ],
        }
        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Prefer /api/generate for multimodal stability across Ollama versions/models.
            generate_url = f"{base_url}/api/generate"
            generate_payload = {
                "model": self.config.model,
                "prompt": user_content,
                "system": system,
                "images": encoded_images,
                "stream": False,
                "format": "json",
                "options": {"temperature": self.config.temperature},
            }
            logger.info(
                "Calling Ollama /api/generate model=%s images=%s timeout=%ss",
                self.config.model,
                len(encoded_images),
                self.config.timeout_seconds,
            )
            try:
                response = await client.post(generate_url, json=generate_payload)
            except httpx.HTTPStatusError as exc:
                raise ValueError(f"Ollama request timed out after {self.config.timeout_seconds}s while generating image-aware response.") from exc
            except httpx.TimeoutException as exc:
                raise ValueError(f"Ollama request timed out after {self.config.timeout_seconds}s while generating image-aware response.") from exc
            except httpx.HTTPError as exc:
                raise ValueError(f"Ollama request failed: {exc}") from exc

            # Some setups may expose /api/chat but not /api/generate for this path/version.
            if response.status_code == 404:
                logger.warning("Ollama /api/generate returned 404. Falling back to /api/chat.")
                try:
                    logger.info(
                        "Calling Ollama /api/chat model=%s images=%s timeout=%ss",
                        self.config.model,
                        len(encoded_images),
                        self.config.timeout_seconds,
                    )
                    chat_response = await client.post(chat_url, json=chat_payload)
                    if chat_response.status_code >= 400:
                        detail = chat_response.text.strip()
                        raise ValueError(f"Ollama /api/chat failed: HTTP {chat_response.status_code} {detail}")
                    data = chat_response.json()
                    message = data.get("message") or {}
                    raw_response = (message.get("content") or "").strip()
                    return self._parse_json_response(raw_response)
                except httpx.TimeoutException as exc:
                    raise ValueError(f"Ollama /api/chat timed out after {self.config.timeout_seconds}s.") from exc

            if response.status_code >= 400:
                detail = response.text.strip()
                if "model" in detail.lower() and "not found" in detail.lower():
                    raise ValueError(
                        f"Ollama model '{self.config.model}' not found. Run `ollama pull {self.config.model}`."
                    )
                raise ValueError(f"Ollama /api/generate failed: HTTP {response.status_code} {detail}")
            data = response.json()
            raw_response = (data.get("response") or "").strip()
            if raw_response:
                return self._parse_json_response(raw_response)
            thinking_response = (data.get("thinking") or "").strip()
            if thinking_response:
                logger.warning(
                    "Ollama /api/generate returned empty response field. Trying to parse thinking field."
                )
                return self._parse_json_response(thinking_response)

            # Some model/runtime combos return empty response from /api/generate.
            logger.warning(
                "Ollama /api/generate returned empty response. Trying /api/chat fallback."
            )
            try:
                logger.info(
                    "Calling Ollama /api/chat model=%s images=%s timeout=%ss",
                    self.config.model,
                    len(encoded_images),
                    self.config.timeout_seconds,
                )
                chat_response = await client.post(chat_url, json=chat_payload)
                if chat_response.status_code >= 400:
                    detail = chat_response.text.strip()
                    raise ValueError(f"Ollama /api/chat failed: HTTP {chat_response.status_code} {detail}")
                chat_data = chat_response.json()
                message = chat_data.get("message") or {}
                chat_raw = (message.get("content") or "").strip()
                if chat_raw:
                    return self._parse_json_response(chat_raw)
                raise ValueError("Model returned empty response from both /api/generate and /api/chat")
            except httpx.TimeoutException as exc:
                raise ValueError(f"Ollama /api/chat timed out after {self.config.timeout_seconds}s.") from exc

    @staticmethod
    def _normalize_image_for_ollama(image_bytes: bytes) -> bytes:
        """Re-encode image as PNG to avoid provider-specific decoder issues."""
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                normalized = img.convert("RGB")
                out = io.BytesIO()
                normalized.save(out, format="PNG")
                return out.getvalue()
        except Exception:
            # If Pillow can't decode, fall back to original bytes.
            return image_bytes

    @staticmethod
    def _parse_json_response(raw_response: str) -> dict[str, Any]:
        if not raw_response:
            raise ValueError("Model returned empty response")
        candidate = raw_response.strip()
        # Models often wrap JSON in markdown fences; strip them before parsing.
        if candidate.startswith("```"):
            parts = [part.strip() for part in candidate.split("```") if part.strip()]
            for part in parts:
                if part.lower().startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{") and part.endswith("}"):
                    candidate = part
                    break
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            # Best-effort: extract first JSON object from noisy responses.
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                extracted = candidate[start : end + 1]
                try:
                    parsed = json.loads(extracted)
                except json.JSONDecodeError as inner_exc:
                    logger.warning(
                        "Failed to parse model response as JSON. snippet=%s",
                        candidate[:300],
                    )
                    raise ValueError(f"Model returned invalid JSON: {candidate[:300]}") from inner_exc
            else:
                logger.warning(
                    "Model response did not contain JSON object. snippet=%s",
                    candidate[:300],
                )
                raise ValueError(f"Model returned invalid JSON: {candidate[:300]}") from exc
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
            "Each attribute must have: name, data_type (text|number|date|boolean|select|tags), is_required, options.\n"
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
        ai_attributes = [
            attr
            for attr in category.attributes
            if getattr(attr, "plugin_field_key", None) in COMIC_AI_ALLOWED_FIELD_KEYS
        ]
        if not ai_attributes:
            raise ValueError("No AI-eligible comic fields found in selected category.")

        attributes_payload = [
            {
                "id": str(attr.id),
                "name": attr.name,
                "data_type": attr.data_type,
                "is_required": attr.is_required,
                "options": attr.options,
            }
            for attr in ai_attributes
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
        filtered_values = self._normalize_extracted_values(values, category.attributes)

        output: dict[str, Any] = {
            "values": filtered_values,
            "confidence": self._normalize_confidence(result.get("confidence")),
            "notes": self._normalize_notes(result.get("notes")),
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

    async def suggest_comic_metadata(
        self,
        *,
        category_id: UUID,
        title: str,
        account_id: UUID,
        item_id: str,
        cover_account_id: UUID | None = None,
        cover_item_id: str | None = None,
    ) -> dict[str, Any]:
        config = await self.get_config()
        if not config.enabled:
            raise ValueError("AI is disabled in runtime settings")
        if config.provider != "ollama":
            raise ValueError(f"Provider '{config.provider}' not implemented yet")
        if not self._is_vision_model_name(config.model):
            raise ValueError(
                "Configured AI model is not vision-capable for comic suggestions. "
                "Set a vision model in Admin > Local AI (example: qwen3-vl:8b, qwen2.5vl:7b, gemma3)."
            )

        category = await self._get_category_with_attributes(category_id)
        ai_attributes = [
            attr
            for attr in category.attributes
            if getattr(attr, "plugin_field_key", None) in COMIC_AI_ALLOWED_FIELD_KEYS
        ]
        if not ai_attributes:
            raise ValueError("No AI-eligible comic fields found in selected category.")
        attributes_payload = [
            {
                "id": str(attr.id),
                "name": attr.name,
                "data_type": attr.data_type,
                "is_required": attr.is_required,
                "options": attr.options,
            }
            for attr in ai_attributes
        ]

        if not cover_item_id:
            raise ValueError("Cover is required for comic AI suggestions. Run Map Comics first.")

        resolved_cover_account_id = cover_account_id or account_id
        account = await self.session.get(LinkedAccount, resolved_cover_account_id)
        if not account:
            raise ValueError(f"Cover account not found: {resolved_cover_account_id}")

        token_manager = TokenManager(self.session)
        client = build_drive_client(account, token_manager)
        logger.info(
            "Comic AI suggestion started account_id=%s item_id=%s cover_account_id=%s cover_item_id=%s model=%s",
            account_id,
            item_id,
            resolved_cover_account_id,
            cover_item_id,
            config.model,
        )
        try:
            _, image_bytes = await client.download_file_bytes(account, cover_item_id)
        except Exception as exc:
            logger.exception(
                "Comic AI cover download failed account_id=%s item_id=%s cover_account_id=%s cover_item_id=%s",
                account_id,
                item_id,
                resolved_cover_account_id,
                cover_item_id,
            )
            raise ValueError(f"Failed to download cover for AI suggestion: {exc}") from exc
        if not image_bytes:
            logger.error(
                "Comic AI cover download returned empty bytes account_id=%s item_id=%s cover_account_id=%s cover_item_id=%s",
                account_id,
                item_id,
                resolved_cover_account_id,
                cover_item_id,
            )
            raise ValueError("Cover image download returned empty bytes.")
        cover_bytes = [image_bytes]
        logger.info(
            "Comic AI cover prepared account_id=%s item_id=%s cover_item_id=%s bytes=%s",
            account_id,
            item_id,
            cover_item_id,
            len(image_bytes),
        )

        system = (
            "You extract comic metadata suggestions from title and cover image.\n"
            "Return strict JSON object with keys: suggestions, notes.\n"
            "suggestions must be an object where keys are attribute IDs exactly as provided.\n"
            "Each suggestion value must be an object with keys: value, confidence.\n"
            "confidence must be between 0 and 1.\n"
            "Always return an entry for every provided attribute ID, even when uncertain.\n"
            "When uncertain, keep a best-effort guess and use low confidence.\n"
            "Never add keys not listed in the attributes payload."
        )
        user_content = (
            f"Category: {category.name}\n"
            f"Attributes JSON:\n{json.dumps(attributes_payload, ensure_ascii=True)}\n\n"
            f"Comic title:\n{title}\n\n"
            "Infer best-effort values for all attributes. Do not omit attributes."
        )
        try:
            result = await OllamaClient(config).generate_json_with_images(
                user_content=user_content,
                system=system,
                images=cover_bytes,
            )
        except ValueError as exc:
            if "empty response" not in str(exc).lower():
                raise
            logger.warning(
                "Comic AI returned empty response after endpoint fallbacks. Returning empty suggestions. account_id=%s item_id=%s model=%s",
                account_id,
                item_id,
                config.model,
            )
            now_iso = datetime.now(UTC).isoformat()
            fallback_suggestions = {
                str(attr.id): {
                    "value": None,
                    "confidence": 0.0,
                    "source": "ai",
                    "model": config.model,
                    "generated_at": now_iso,
                    "notes": "Model returned empty response",
                }
                for attr in ai_attributes
            }
            return {
                "category_id": category_id,
                "account_id": account_id,
                "item_id": item_id,
                "suggestions": fallback_suggestions,
                "notes": "Model returned empty response",
                "model": config.model,
            }

        raw_suggestions = result.get("suggestions", {})
        if isinstance(raw_suggestions, str):
            try:
                raw_suggestions = json.loads(raw_suggestions)
            except json.JSONDecodeError:
                logger.warning(
                    "Comic AI suggestions came as non-JSON string. snippet=%s",
                    raw_suggestions[:300],
                )
                raw_suggestions = {}
        if not isinstance(raw_suggestions, (dict, list)):
            logger.warning(
                "Comic AI suggestions came with unexpected type=%s. Forcing empty suggestions.",
                type(raw_suggestions).__name__,
            )
            raw_suggestions = {}

        normalized_values = self._normalize_extracted_values(raw_suggestions, ai_attributes)
        normalized_suggestions: dict[str, dict[str, Any]] = {}
        now_iso = datetime.now(UTC).isoformat()

        confidence_source = result.get("confidence")
        confidence_map = confidence_source if isinstance(confidence_source, dict) else {}
        model_name = config.model
        notes = self._normalize_notes(result.get("notes"))

        attr_id_set = {str(attr.id) for attr in ai_attributes}
        for attr_id in attr_id_set:
            entry = raw_suggestions.get(attr_id) if isinstance(raw_suggestions, dict) else None
            value = normalized_values.get(attr_id)
            confidence: float | None = None
            if isinstance(entry, dict):
                confidence = self._normalize_confidence(entry.get("confidence"))
                if "value" in entry:
                    value = entry.get("value")
            if confidence is None and isinstance(confidence_map, dict):
                confidence = self._normalize_confidence(confidence_map.get(attr_id))
            if confidence is None:
                confidence = 0.0
            normalized_suggestions[attr_id] = {
                "value": value,
                "confidence": confidence,
                "source": "ai",
                "model": model_name,
                "generated_at": now_iso,
                "notes": notes,
            }

        logger.info(
            "Comic AI suggestion completed account_id=%s item_id=%s suggested_fields=%s",
            account_id,
            item_id,
            len(normalized_suggestions),
        )

        return {
            "category_id": category_id,
            "account_id": account_id,
            "item_id": item_id,
            "suggestions": normalized_suggestions,
            "notes": notes,
            "model": model_name,
        }

    @staticmethod
    def _is_vision_model_name(model_name: str | None) -> bool:
        name = (model_name or "").strip().lower()
        if not name:
            return False
        markers = ("-vl", ".vl", "vl:", "llava", "gemma3")
        return any(marker in name for marker in markers)

    @staticmethod
    def _normalize_extracted_values(values: Any, attributes: list[Any]) -> dict[str, Any]:
        if isinstance(values, list):
            mapped: dict[str, Any] = {}
            for entry in values:
                if not isinstance(entry, dict):
                    continue
                key = (
                    entry.get("attribute_id")
                    or entry.get("id")
                    or entry.get("attribute")
                    or entry.get("name")
                )
                if key is None:
                    continue
                raw_value = entry.get("value")
                if isinstance(raw_value, dict) and "value" in raw_value:
                    raw_value = raw_value["value"]
                mapped[str(key)] = raw_value
            values = mapped

        if not isinstance(values, dict):
            raise ValueError("AI response 'values' must be an object")

        allowed_attr_ids = {str(attr.id): attr for attr in attributes}
        name_to_id = {
            str(attr.name).strip().lower(): str(attr.id)
            for attr in attributes
            if getattr(attr, "name", None)
        }

        filtered_values: dict[str, Any] = {}
        for raw_key, raw_value in values.items():
            key = str(raw_key).strip()
            attr_id = key if key in allowed_attr_ids else name_to_id.get(key.lower())
            if not attr_id:
                continue

            value = raw_value
            if isinstance(value, dict) and "value" in value:
                value = value["value"]
            filtered_values[attr_id] = value

        return filtered_values

    @staticmethod
    def _normalize_confidence(confidence: Any) -> float | None:
        if confidence is None:
            return None

        if isinstance(confidence, bool):
            return 1.0 if confidence else 0.0

        if isinstance(confidence, (int, float)):
            return float(confidence)

        if isinstance(confidence, str):
            try:
                return float(confidence.strip())
            except ValueError:
                return None

        if isinstance(confidence, dict):
            numeric_values: list[float] = []
            for value in confidence.values():
                if isinstance(value, bool):
                    numeric_values.append(1.0 if value else 0.0)
                elif isinstance(value, (int, float)):
                    numeric_values.append(float(value))
                elif isinstance(value, str):
                    try:
                        numeric_values.append(float(value.strip()))
                    except ValueError:
                        continue
            if not numeric_values:
                return None
            return sum(numeric_values) / len(numeric_values)

        if isinstance(confidence, list):
            numeric_values: list[float] = []
            for value in confidence:
                if isinstance(value, bool):
                    numeric_values.append(1.0 if value else 0.0)
                elif isinstance(value, (int, float)):
                    numeric_values.append(float(value))
                elif isinstance(value, str):
                    try:
                        numeric_values.append(float(value.strip()))
                    except ValueError:
                        continue
            if not numeric_values:
                return None
            return sum(numeric_values) / len(numeric_values)

        return None

    @staticmethod
    def _normalize_notes(notes: Any) -> str | None:
        if notes is None:
            return None
        if isinstance(notes, str):
            return notes
        if isinstance(notes, (int, float, bool)):
            return str(notes)
        try:
            return json.dumps(notes, ensure_ascii=True)
        except TypeError:
            return str(notes)

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
