"""Managed metadata plugin helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import MetadataAttribute, MetadataCategory, MetadataPlugin

COMIC_PLUGIN_KEY = "comicrack_core"


@dataclass(frozen=True, slots=True)
class PluginFieldSpec:
    key: str
    name: str
    data_type: str
    is_required: bool = False
    options: dict[str, Any] | None = None


COMIC_PLUGIN_FIELDS: list[PluginFieldSpec] = [
    PluginFieldSpec("series", "Series", "text"),
    PluginFieldSpec("volume", "Volume", "number"),
    PluginFieldSpec("issue_number", "Issue Number", "text"),
    PluginFieldSpec("title", "Title", "text"),
    PluginFieldSpec("year", "Year", "number"),
    PluginFieldSpec("month", "Month", "number"),
    PluginFieldSpec("day", "Day", "number"),
    PluginFieldSpec("publisher", "Publisher", "text"),
    PluginFieldSpec("imprint", "Imprint", "text"),
    PluginFieldSpec("writer", "Writer", "text"),
    PluginFieldSpec("penciller", "Penciller", "text"),
    PluginFieldSpec("inker", "Inker", "text"),
    PluginFieldSpec("colorist", "Colorist", "text"),
    PluginFieldSpec("letterer", "Letterer", "text"),
    PluginFieldSpec("genre", "Genre", "text"),
    PluginFieldSpec("summary", "Summary", "text"),
    PluginFieldSpec("language", "Language", "text"),
    PluginFieldSpec("manga", "Manga", "boolean"),
    PluginFieldSpec("black_and_white", "Black & White", "boolean"),
    PluginFieldSpec("cover_item_id", "Cover Item ID", "text"),
    PluginFieldSpec("cover_filename", "Cover Filename", "text"),
    PluginFieldSpec("page_count", "Page Count", "number"),
    PluginFieldSpec("file_size", "File Size", "number"),
    PluginFieldSpec("file_format", "File Format", "text"),
]


def _build_field_index() -> dict[str, PluginFieldSpec]:
    return {field.key: field for field in COMIC_PLUGIN_FIELDS}


class MetadataPluginService:
    """Service for plugin-backed metadata categories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_plugins(self) -> list[MetadataPlugin]:
        try:
            stmt = select(MetadataPlugin).order_by(MetadataPlugin.key.asc())
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except OperationalError as exc:
            if "no such table: metadata_plugins" in str(exc).lower():
                return []
            raise

    async def activate_comic_plugin(self) -> MetadataPlugin:
        plugin = await self._get_or_create_plugin_row(
            COMIC_PLUGIN_KEY,
            "ComicRack Core",
            "Managed comic metadata schema with locked attributes.",
        )
        category = await self._ensure_comic_category()
        plugin.is_active = True
        plugin.category_id = category.id
        category.is_active = True
        return plugin

    async def deactivate_comic_plugin(self) -> MetadataPlugin:
        stmt = select(MetadataPlugin).where(MetadataPlugin.key == COMIC_PLUGIN_KEY)
        result = await self.session.execute(stmt)
        plugin = result.scalar_one_or_none()
        if plugin is None:
            plugin = await self._get_or_create_plugin_row(
                COMIC_PLUGIN_KEY,
                "ComicRack Core",
                "Managed comic metadata schema with locked attributes.",
            )
        plugin.is_active = False

        if plugin.category_id:
            category = await self.session.get(MetadataCategory, plugin.category_id)
            if category:
                category.is_active = False

        return plugin

    async def get_active_comic_category(self) -> MetadataCategory | None:
        stmt = (
            select(MetadataCategory)
            .where(
                MetadataCategory.plugin_key == COMIC_PLUGIN_KEY,
                MetadataCategory.managed_by_plugin.is_(True),
                MetadataCategory.is_active.is_(True),
            )
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def ensure_active_comic_category(self) -> MetadataCategory:
        category = await self.get_active_comic_category()
        if category is None:
            raise ValueError("Comic plugin is not active. Activate comicrack_core first.")
        return category

    async def comic_attribute_id_map(self) -> dict[str, str]:
        category = await self.ensure_active_comic_category()
        return {
            attr.plugin_field_key: str(attr.id)
            for attr in category.attributes
            if attr.plugin_field_key
        }

    async def _get_or_create_plugin_row(
        self,
        key: str,
        name: str,
        description: str | None,
    ) -> MetadataPlugin:
        stmt = select(MetadataPlugin).where(MetadataPlugin.key == key)
        result = await self.session.execute(stmt)
        plugin = result.scalar_one_or_none()
        if plugin:
            if name:
                plugin.name = name
            if description is not None:
                plugin.description = description
            return plugin

        plugin = MetadataPlugin(
            key=key,
            name=name,
            description=description,
            is_active=False,
            category_id=None,
        )
        self.session.add(plugin)
        await self.session.flush()
        return plugin

    async def _ensure_comic_category(self) -> MetadataCategory:
        stmt = (
            select(MetadataCategory)
            .where(
                MetadataCategory.plugin_key == COMIC_PLUGIN_KEY,
                MetadataCategory.managed_by_plugin.is_(True),
            )
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()

        if category is None:
            conflict_stmt = select(MetadataCategory).where(MetadataCategory.name == "Comics")
            conflict = (await self.session.execute(conflict_stmt)).scalar_one_or_none()
            if conflict and not conflict.managed_by_plugin:
                raise ValueError("Category name 'Comics' already exists and is not plugin-managed.")

            category = MetadataCategory(
                name="Comics",
                description="Comic metadata managed by plugin comicrack_core.",
                is_active=True,
                managed_by_plugin=True,
                plugin_key=COMIC_PLUGIN_KEY,
                is_locked=True,
            )
            self.session.add(category)
            await self.session.flush()

        category.is_active = True
        category.managed_by_plugin = True
        category.plugin_key = COMIC_PLUGIN_KEY
        category.is_locked = True

        attrs_stmt = select(MetadataAttribute).where(MetadataAttribute.category_id == category.id)
        attrs_result = await self.session.execute(attrs_stmt)
        category_attrs = attrs_result.scalars().all()
        existing_by_key = {
            attr.plugin_field_key: attr
            for attr in category_attrs
            if attr.plugin_field_key
        }
        specs = _build_field_index()
        for field_key, spec in specs.items():
            db_attr = existing_by_key.get(field_key)
            if db_attr is None:
                db_attr = MetadataAttribute(
                    category_id=category.id,
                    name=spec.name,
                    data_type=spec.data_type,
                    options=spec.options,
                    is_required=spec.is_required,
                    managed_by_plugin=True,
                    plugin_key=COMIC_PLUGIN_KEY,
                    plugin_field_key=field_key,
                    is_locked=True,
                )
                self.session.add(db_attr)
            else:
                db_attr.name = spec.name
                db_attr.data_type = spec.data_type
                db_attr.options = spec.options
                db_attr.is_required = spec.is_required
                db_attr.managed_by_plugin = True
                db_attr.plugin_key = COMIC_PLUGIN_KEY
                db_attr.plugin_field_key = field_key
                db_attr.is_locked = True

        await self.session.flush()

        refreshed_stmt = (
            select(MetadataCategory)
            .where(MetadataCategory.id == category.id)
            .options(selectinload(MetadataCategory.attributes))
        )
        refreshed = await self.session.execute(refreshed_stmt)
        category_loaded = refreshed.scalar_one_or_none()
        if category_loaded is None:
            raise ValueError("Failed to load plugin category")
        return category_loaded
