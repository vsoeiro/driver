"""Dynamic metadata-library settings registry persisted in app_settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.db.models import AppSetting, MetadataPlugin
from backend.services.metadata_libraries.implementations.comics.schema import (
    COMICS_LIBRARY_KEY,
)

# Keep persisted setting keys stable for backward compatibility.
METADATA_LIBRARY_PREFIX = "plugin:"


@dataclass(frozen=True, slots=True)
class MetadataLibrarySettingFieldSpec:
    key: str
    label: str
    input_type: str
    description: str | None = None
    required: bool = False
    default: Any = None
    minimum: int | None = None
    maximum: int | None = None
    placeholder: str | None = None
    account_field_key: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataLibrarySettingSpec:
    library_key: str
    library_name: str
    description: str | None
    schema_version: int
    fields: tuple[MetadataLibrarySettingFieldSpec, ...]


@dataclass(frozen=True, slots=True)
class ComicsRuntimeSettings:
    storage_account_id: str | None
    storage_parent_folder_id: str
    storage_folder_name: str
    max_width: int
    max_height: int
    target_bytes: int
    quality_steps: tuple[int, ...]


def _comics_library_setting_spec() -> MetadataLibrarySettingSpec:
    cfg = get_settings()
    return MetadataLibrarySettingSpec(
        library_key=COMICS_LIBRARY_KEY,
        library_name="Comics Core",
        description="Storage and optimization settings for comic cover extraction.",
        schema_version=1,
        fields=(
            MetadataLibrarySettingFieldSpec(
                key="cover_storage_target",
                label="Cover Destination",
                input_type="folder_target",
                description="Choose account and folder where extracted covers are uploaded.",
                default={
                    "account_id": cfg.comic_cover_storage_account_id or "",
                    "folder_id": cfg.comic_cover_storage_parent_folder_id,
                    "folder_path": "Root",
                },
            ),
            MetadataLibrarySettingFieldSpec(
                key="cover_storage_folder_name",
                label="Cover Folder Name",
                input_type="text",
                description="Subfolder name created under destination to store covers.",
                default=cfg.comic_cover_storage_folder_name,
                placeholder="__driver_comic_covers__",
            ),
            MetadataLibrarySettingFieldSpec(
                key="cover_max_width",
                label="Cover Max Width",
                input_type="number",
                description="Maximum cover width in pixels after optimization.",
                default=cfg.comic_cover_max_width,
                minimum=100,
                maximum=4000,
            ),
            MetadataLibrarySettingFieldSpec(
                key="cover_max_height",
                label="Cover Max Height",
                input_type="number",
                description="Maximum cover height in pixels after optimization.",
                default=cfg.comic_cover_max_height,
                minimum=100,
                maximum=6000,
            ),
            MetadataLibrarySettingFieldSpec(
                key="cover_target_bytes",
                label="Cover Target Size (bytes)",
                input_type="number",
                description="Target cover file size used when selecting JPEG quality.",
                default=cfg.comic_cover_target_bytes,
                minimum=20000,
                maximum=5_000_000,
            ),
            MetadataLibrarySettingFieldSpec(
                key="cover_jpeg_quality_steps",
                label="JPEG Quality Steps",
                input_type="text",
                description="Comma-separated JPEG qualities used in compression fallback.",
                default=cfg.comic_cover_jpeg_quality_steps,
                placeholder="84,78,72,66,60",
            ),
        ),
    )


METADATA_LIBRARY_SETTINGS_REGISTRY: dict[str, MetadataLibrarySettingSpec] = {
    COMICS_LIBRARY_KEY: _comics_library_setting_spec(),
}


def setting_db_key(library_key: str, field_key: str) -> str:
    return f"{METADATA_LIBRARY_PREFIX}{library_key}:{field_key}"


class MetadataLibrarySettingsService:
    """Read/update metadata-library settings dynamically using a registry."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active_metadata_library_configs(self) -> list[dict[str, Any]]:
        active_libraries = await self._active_metadata_libraries()
        output: list[dict[str, Any]] = []
        for library in active_libraries:
            spec = METADATA_LIBRARY_SETTINGS_REGISTRY.get(library.key)
            if spec is None:
                continue
            rows = await self._ensure_library_defaults(spec)
            fields = []
            for field_spec in spec.fields:
                row = rows[setting_db_key(spec.library_key, field_spec.key)]
                parsed_value = self._parse_value(field_spec, row.value)
                fields.append(
                    {
                        "key": field_spec.key,
                        "label": field_spec.label,
                        "input_type": field_spec.input_type,
                        "description": field_spec.description,
                        "required": field_spec.required,
                        "minimum": field_spec.minimum,
                        "maximum": field_spec.maximum,
                        "placeholder": field_spec.placeholder,
                        "account_field_key": field_spec.account_field_key,
                        "value": parsed_value,
                    }
                )
            output.append(
                {
                    "plugin_key": library.key,  # kept for public API compatibility
                    "plugin_name": library.name or spec.library_name,
                    "plugin_description": library.description or spec.description,
                    "capabilities": {
                        "schema_version": spec.schema_version,
                        "supported_input_types": sorted(
                            {field.input_type for field in spec.fields}
                        ),
                        "actions": ["reindex_covers"]
                        if spec.library_key == COMICS_LIBRARY_KEY
                        else [],
                    },
                    "fields": fields,
                }
            )
        return output

    async def update_metadata_library_configs(
        self, payload: dict[str, dict[str, Any]] | None
    ) -> None:
        if not payload:
            return
        active_keys = {
            library.key for library in await self._active_metadata_libraries()
        }
        changed = False
        for library_key, values in payload.items():
            spec = METADATA_LIBRARY_SETTINGS_REGISTRY.get(library_key)
            if spec is None:
                raise ValueError(
                    f"Unknown metadata library settings key: {library_key}"
                )
            if library_key not in active_keys:
                raise ValueError(
                    f"Metadata library '{library_key}' must be active before updating settings."
                )

            rows = await self._ensure_library_defaults(spec)
            for field_key, raw_value in values.items():
                field_spec = next(
                    (field for field in spec.fields if field.key == field_key), None
                )
                if field_spec is None:
                    raise ValueError(
                        f"Unknown setting '{field_key}' for metadata library '{library_key}'."
                    )
                validated = self._validate_value(field_spec, raw_value)
                row = rows[setting_db_key(library_key, field_key)]
                row.value = self._serialize_value(field_spec, validated)
                changed = True
        if changed:
            await self.session.commit()

    async def get_comics_runtime_settings(self) -> ComicsRuntimeSettings:
        spec = METADATA_LIBRARY_SETTINGS_REGISTRY[COMICS_LIBRARY_KEY]
        rows = await self._ensure_library_defaults(spec)
        values: dict[str, Any] = {}
        for field in spec.fields:
            row = rows[setting_db_key(COMICS_LIBRARY_KEY, field.key)]
            values[field.key] = self._parse_value(field, row.value)

        target = values["cover_storage_target"] or {}
        account_id = (target.get("account_id") or "").strip() or None
        folder_id = (target.get("folder_id") or "root").strip() or "root"
        folder_name = (
            str(values["cover_storage_folder_name"]).strip()
            or "__driver_comic_covers__"
        )
        quality_steps = self._parse_quality_steps(
            str(values["cover_jpeg_quality_steps"])
        )
        return ComicsRuntimeSettings(
            storage_account_id=account_id,
            storage_parent_folder_id=folder_id,
            storage_folder_name=folder_name,
            max_width=max(64, int(values["cover_max_width"])),
            max_height=max(64, int(values["cover_max_height"])),
            target_bytes=max(10_000, int(values["cover_target_bytes"])),
            quality_steps=quality_steps,
        )

    async def _active_metadata_libraries(self) -> list[MetadataPlugin]:
        try:
            stmt = select(MetadataPlugin).where(MetadataPlugin.is_active.is_(True))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except OperationalError as exc:
            if "no such table: metadata_plugins" in str(exc).lower():
                return []
            raise

    async def _ensure_library_defaults(
        self, spec: MetadataLibrarySettingSpec
    ) -> dict[str, AppSetting]:
        keys = [setting_db_key(spec.library_key, field.key) for field in spec.fields]
        result = await self.session.execute(
            select(AppSetting).where(AppSetting.key.in_(keys))
        )
        rows = {row.key: row for row in result.scalars().all()}
        changed = False
        for field in spec.fields:
            db_key = setting_db_key(spec.library_key, field.key)
            if db_key in rows:
                continue
            row = AppSetting(
                key=db_key,
                value=self._serialize_value(field, field.default),
                description=f"[{spec.library_key}] {field.label}",
            )
            self.session.add(row)
            rows[db_key] = row
            changed = True
        if changed:
            await self.session.commit()
        return rows

    def _validate_value(
        self, field: MetadataLibrarySettingFieldSpec, value: Any
    ) -> Any:
        if field.input_type == "number":
            parsed = int(value)
            if field.minimum is not None and parsed < field.minimum:
                raise ValueError(f"{field.key} must be >= {field.minimum}")
            if field.maximum is not None and parsed > field.maximum:
                raise ValueError(f"{field.key} must be <= {field.maximum}")
            return parsed
        if field.input_type == "folder_target":
            if not isinstance(value, dict):
                raise ValueError(f"{field.key} must be an object")
            folder_id = str(value.get("folder_id") or "root").strip() or "root"
            account_id = str(value.get("account_id") or "").strip()
            folder_path = str(value.get("folder_path") or "Root").strip() or "Root"
            return {
                "account_id": account_id,
                "folder_id": folder_id,
                "folder_path": folder_path,
            }
        if field.input_type == "text":
            text = str(value if value is not None else "").strip()
            if field.required and not text:
                raise ValueError(f"{field.key} is required")
            if field.key == "cover_jpeg_quality_steps":
                _ = self._parse_quality_steps(text)
            return text
        return value

    @staticmethod
    def _serialize_value(field: MetadataLibrarySettingFieldSpec, value: Any) -> str:
        if field.input_type == "folder_target":
            return json.dumps(value or {}, ensure_ascii=True)
        return str(value if value is not None else "")

    @staticmethod
    def _parse_value(field: MetadataLibrarySettingFieldSpec, value: str) -> Any:
        if field.input_type == "number":
            try:
                return int(value)
            except (TypeError, ValueError):
                return int(field.default)
        if field.input_type == "folder_target":
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
            return field.default
        return value

    @staticmethod
    def _parse_quality_steps(value: str) -> tuple[int, ...]:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        parsed: list[int] = []
        for part in parts:
            quality = int(part)
            if not 1 <= quality <= 100:
                raise ValueError("cover_jpeg_quality_steps values must be in [1, 100]")
            parsed.append(quality)
        if not parsed:
            raise ValueError("cover_jpeg_quality_steps cannot be empty")
        return tuple(parsed)
