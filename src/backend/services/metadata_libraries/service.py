"""Metadata library management service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import MetadataAttribute, MetadataCategory, MetadataPlugin
from backend.services.metadata_libraries.implementations.books.schema import (
    BOOKS_LIBRARY_FIELDS,
    BOOKS_LIBRARY_KEY,
)
from backend.services.metadata_libraries.implementations.comics.schema import (
    COMICS_LIBRARY_FIELDS,
    COMICS_LIBRARY_KEY,
    MetadataLibraryFieldSpec,
)
from backend.services.metadata_libraries.implementations.images.schema import (
    IMAGES_LIBRARY_FIELDS,
    IMAGES_LIBRARY_KEY,
)


def _build_field_index() -> dict[str, MetadataLibraryFieldSpec]:
    return {field.key: field for field in COMICS_LIBRARY_FIELDS}


def _build_images_field_index() -> dict[str, MetadataLibraryFieldSpec]:
    return {field.key: field for field in IMAGES_LIBRARY_FIELDS}


def _build_books_field_index() -> dict[str, MetadataLibraryFieldSpec]:
    return {field.key: field for field in BOOKS_LIBRARY_FIELDS}


class MetadataLibraryService:
    """Service for library-managed metadata schemas."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_libraries(self) -> list[MetadataPlugin]:
        try:
            stmt = select(MetadataPlugin).order_by(MetadataPlugin.key.asc())
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except OperationalError as exc:
            if "no such table: metadata_plugins" in str(exc).lower():
                return []
            raise

    async def activate_comics_library(self) -> MetadataPlugin:
        library = await self._get_or_create_library_row(
            COMICS_LIBRARY_KEY,
            "Comics Core",
            "Comics by Metadata Library.",
        )
        category = await self._ensure_comics_category()
        library.is_active = True
        library.category_id = category.id
        category.is_active = True
        return library

    async def activate_images_library(self) -> MetadataPlugin:
        library = await self._get_or_create_library_row(
            IMAGES_LIBRARY_KEY,
            "Images Core",
            "Images by Metadata Library.",
        )
        category = await self._ensure_images_category()
        library.is_active = True
        library.category_id = category.id
        category.is_active = True
        return library

    async def activate_books_library(self) -> MetadataPlugin:
        library = await self._get_or_create_library_row(
            BOOKS_LIBRARY_KEY,
            "Books Core",
            "Books by Metadata Library.",
        )
        category = await self._ensure_books_category()
        library.is_active = True
        library.category_id = category.id
        category.is_active = True
        return library

    async def deactivate_comics_library(self) -> MetadataPlugin:
        stmt = select(MetadataPlugin).where(MetadataPlugin.key == COMICS_LIBRARY_KEY)
        result = await self.session.execute(stmt)
        library = result.scalar_one_or_none()
        if library is None:
            library = await self._get_or_create_library_row(
                COMICS_LIBRARY_KEY,
                "Comics Core",
                "Comics by Metadata Library.",
            )
        library.is_active = False

        if library.category_id:
            category = await self.session.get(MetadataCategory, library.category_id)
            if category:
                category.is_active = False

        return library

    async def deactivate_images_library(self) -> MetadataPlugin:
        stmt = select(MetadataPlugin).where(MetadataPlugin.key == IMAGES_LIBRARY_KEY)
        result = await self.session.execute(stmt)
        library = result.scalar_one_or_none()
        if library is None:
            library = await self._get_or_create_library_row(
                IMAGES_LIBRARY_KEY,
                "Images Core",
                "Images by Metadata Library.",
            )
        library.is_active = False

        if library.category_id:
            category = await self.session.get(MetadataCategory, library.category_id)
            if category:
                category.is_active = False

        return library

    async def deactivate_books_library(self) -> MetadataPlugin:
        stmt = select(MetadataPlugin).where(MetadataPlugin.key == BOOKS_LIBRARY_KEY)
        result = await self.session.execute(stmt)
        library = result.scalar_one_or_none()
        if library is None:
            library = await self._get_or_create_library_row(
                BOOKS_LIBRARY_KEY,
                "Books Core",
                "Books by Metadata Library.",
            )
        library.is_active = False

        if library.category_id:
            category = await self.session.get(MetadataCategory, library.category_id)
            if category:
                category.is_active = False

        return library

    async def get_active_comics_category(self) -> MetadataCategory | None:
        stmt = (
            select(MetadataCategory)
            .where(
                MetadataCategory.plugin_key == COMICS_LIBRARY_KEY,
                MetadataCategory.managed_by_plugin.is_(True),
                MetadataCategory.is_active.is_(True),
            )
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def ensure_active_comics_category(self) -> MetadataCategory:
        category = await self.get_active_comics_category()
        if category is None:
            raise ValueError(
                "Comics metadata library is not active. Activate comics_core first."
            )
        return await self._ensure_comics_category()

    async def get_active_images_category(self) -> MetadataCategory | None:
        stmt = (
            select(MetadataCategory)
            .where(
                MetadataCategory.plugin_key == IMAGES_LIBRARY_KEY,
                MetadataCategory.managed_by_plugin.is_(True),
                MetadataCategory.is_active.is_(True),
            )
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def ensure_active_images_category(self) -> MetadataCategory:
        category = await self.get_active_images_category()
        if category is None:
            await self.activate_images_library()
        return await self._ensure_images_category()

    async def get_active_books_category(self) -> MetadataCategory | None:
        stmt = (
            select(MetadataCategory)
            .where(
                MetadataCategory.plugin_key == BOOKS_LIBRARY_KEY,
                MetadataCategory.managed_by_plugin.is_(True),
                MetadataCategory.is_active.is_(True),
            )
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def ensure_active_books_category(self) -> MetadataCategory:
        category = await self.get_active_books_category()
        if category is None:
            await self.activate_books_library()
        return await self._ensure_books_category()

    async def comics_attribute_id_map(self) -> dict[str, str]:
        category = await self.ensure_active_comics_category()
        return {
            attr.plugin_field_key: str(attr.id)
            for attr in category.attributes
            if attr.plugin_field_key
        }

    async def images_attribute_id_map(self) -> dict[str, str]:
        category = await self.ensure_active_images_category()
        return {
            attr.plugin_field_key: str(attr.id)
            for attr in category.attributes
            if attr.plugin_field_key
        }

    async def books_attribute_id_map(self) -> dict[str, str]:
        category = await self.ensure_active_books_category()
        return {
            attr.plugin_field_key: str(attr.id)
            for attr in category.attributes
            if attr.plugin_field_key
        }

    async def _get_or_create_library_row(
        self,
        key: str,
        name: str,
        description: str | None,
    ) -> MetadataPlugin:
        stmt = select(MetadataPlugin).where(MetadataPlugin.key == key)
        result = await self.session.execute(stmt)
        library = result.scalar_one_or_none()
        if library:
            if name:
                library.name = name
            if description is not None:
                library.description = description
            return library

        library = MetadataPlugin(
            key=key,
            name=name,
            description=description,
            is_active=False,
            category_id=None,
        )
        self.session.add(library)
        await self.session.flush()
        return library

    async def _ensure_comics_category(self) -> MetadataCategory:
        stmt = (
            select(MetadataCategory)
            .where(
                MetadataCategory.plugin_key == COMICS_LIBRARY_KEY,
                MetadataCategory.managed_by_plugin.is_(True),
            )
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()

        if category is None:
            conflict_stmt = select(MetadataCategory).where(
                MetadataCategory.name == "Comics"
            )
            conflict = (await self.session.execute(conflict_stmt)).scalar_one_or_none()
            if conflict and not conflict.managed_by_plugin:
                raise ValueError(
                    "Category name 'Comics' already exists and is not library-managed."
                )

            category = MetadataCategory(
                name="Comics",
                description="Comics by Metadata Library.",
                is_active=True,
                managed_by_plugin=True,
                plugin_key=COMICS_LIBRARY_KEY,
                is_locked=True,
            )
            self.session.add(category)
            await self.session.flush()

        category.is_active = True
        category.managed_by_plugin = True
        category.plugin_key = COMICS_LIBRARY_KEY
        category.is_locked = True
        category.description = "Comics by Metadata Library."

        attrs_stmt = select(MetadataAttribute).where(
            MetadataAttribute.category_id == category.id
        )
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
                    plugin_key=COMICS_LIBRARY_KEY,
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
                db_attr.plugin_key = COMICS_LIBRARY_KEY
                db_attr.plugin_field_key = field_key
                db_attr.is_locked = True

        valid_keys = set(specs.keys())
        for db_attr in category_attrs:
            if (
                db_attr.plugin_key == COMICS_LIBRARY_KEY
                and db_attr.managed_by_plugin
                and db_attr.plugin_field_key
                and db_attr.plugin_field_key not in valid_keys
            ):
                await self.session.delete(db_attr)

        await self.session.flush()

        refreshed_stmt = (
            select(MetadataCategory)
            .where(MetadataCategory.id == category.id)
            .options(selectinload(MetadataCategory.attributes))
        )
        refreshed = await self.session.execute(refreshed_stmt)
        category_loaded = refreshed.scalar_one_or_none()
        if category_loaded is None:
            raise ValueError("Failed to load metadata library category")
        return category_loaded

    async def _ensure_images_category(self) -> MetadataCategory:
        stmt = (
            select(MetadataCategory)
            .where(
                MetadataCategory.plugin_key == IMAGES_LIBRARY_KEY,
                MetadataCategory.managed_by_plugin.is_(True),
            )
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()

        if category is None:
            conflict_stmt = select(MetadataCategory).where(
                MetadataCategory.name == "Images"
            )
            conflict = (await self.session.execute(conflict_stmt)).scalar_one_or_none()
            if conflict and not conflict.managed_by_plugin:
                raise ValueError(
                    "Category name 'Images' already exists and is not library-managed."
                )

            category = MetadataCategory(
                name="Images",
                description="Images by Metadata Library.",
                is_active=True,
                managed_by_plugin=True,
                plugin_key=IMAGES_LIBRARY_KEY,
                is_locked=True,
            )
            self.session.add(category)
            await self.session.flush()

        category.is_active = True
        category.managed_by_plugin = True
        category.plugin_key = IMAGES_LIBRARY_KEY
        category.is_locked = True
        category.description = "Images by Metadata Library."

        attrs_stmt = select(MetadataAttribute).where(
            MetadataAttribute.category_id == category.id
        )
        attrs_result = await self.session.execute(attrs_stmt)
        category_attrs = attrs_result.scalars().all()
        existing_by_key = {
            attr.plugin_field_key: attr
            for attr in category_attrs
            if attr.plugin_field_key
        }
        specs = _build_images_field_index()
        for field_key, spec in specs.items():
            db_attr = existing_by_key.get(field_key)
            if db_attr is None:
                db_attr = MetadataAttribute(
                    category_id=category.id,
                    name=spec.name,
                    data_type=spec.data_type,
                    options=None,
                    is_required=spec.is_required,
                    managed_by_plugin=True,
                    plugin_key=IMAGES_LIBRARY_KEY,
                    plugin_field_key=field_key,
                    is_locked=True,
                )
                self.session.add(db_attr)
            else:
                db_attr.name = spec.name
                db_attr.data_type = spec.data_type
                db_attr.options = None
                db_attr.is_required = spec.is_required
                db_attr.managed_by_plugin = True
                db_attr.plugin_key = IMAGES_LIBRARY_KEY
                db_attr.plugin_field_key = field_key
                db_attr.is_locked = True

        valid_keys = set(specs.keys())
        for db_attr in category_attrs:
            if (
                db_attr.plugin_key == IMAGES_LIBRARY_KEY
                and db_attr.managed_by_plugin
                and db_attr.plugin_field_key
                and db_attr.plugin_field_key not in valid_keys
            ):
                await self.session.delete(db_attr)

        await self.session.flush()

        refreshed_stmt = (
            select(MetadataCategory)
            .where(MetadataCategory.id == category.id)
            .options(selectinload(MetadataCategory.attributes))
        )
        refreshed = await self.session.execute(refreshed_stmt)
        category_loaded = refreshed.scalar_one_or_none()
        if category_loaded is None:
            raise ValueError("Failed to load metadata library category")
        return category_loaded

    async def _ensure_books_category(self) -> MetadataCategory:
        stmt = (
            select(MetadataCategory)
            .where(
                MetadataCategory.plugin_key == BOOKS_LIBRARY_KEY,
                MetadataCategory.managed_by_plugin.is_(True),
            )
            .options(selectinload(MetadataCategory.attributes))
        )
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()

        if category is None:
            conflict_stmt = select(MetadataCategory).where(
                MetadataCategory.name == "Books"
            )
            conflict = (await self.session.execute(conflict_stmt)).scalar_one_or_none()
            if conflict and not conflict.managed_by_plugin:
                raise ValueError(
                    "Category name 'Books' already exists and is not library-managed."
                )

            category = MetadataCategory(
                name="Books",
                description="Books by Metadata Library.",
                is_active=True,
                managed_by_plugin=True,
                plugin_key=BOOKS_LIBRARY_KEY,
                is_locked=True,
            )
            self.session.add(category)
            await self.session.flush()

        category.is_active = True
        category.managed_by_plugin = True
        category.plugin_key = BOOKS_LIBRARY_KEY
        category.is_locked = True
        category.description = "Books by Metadata Library."

        attrs_stmt = select(MetadataAttribute).where(
            MetadataAttribute.category_id == category.id
        )
        attrs_result = await self.session.execute(attrs_stmt)
        category_attrs = attrs_result.scalars().all()
        existing_by_key = {
            attr.plugin_field_key: attr
            for attr in category_attrs
            if attr.plugin_field_key
        }
        specs = _build_books_field_index()
        for field_key, spec in specs.items():
            db_attr = existing_by_key.get(field_key)
            if db_attr is None:
                db_attr = MetadataAttribute(
                    category_id=category.id,
                    name=spec.name,
                    data_type=spec.data_type,
                    options=None,
                    is_required=spec.is_required,
                    managed_by_plugin=True,
                    plugin_key=BOOKS_LIBRARY_KEY,
                    plugin_field_key=field_key,
                    is_locked=True,
                )
                self.session.add(db_attr)
            else:
                db_attr.name = spec.name
                db_attr.data_type = spec.data_type
                db_attr.options = None
                db_attr.is_required = spec.is_required
                db_attr.managed_by_plugin = True
                db_attr.plugin_key = BOOKS_LIBRARY_KEY
                db_attr.plugin_field_key = field_key
                db_attr.is_locked = True

        valid_keys = set(specs.keys())
        for db_attr in category_attrs:
            if (
                db_attr.plugin_key == BOOKS_LIBRARY_KEY
                and db_attr.managed_by_plugin
                and db_attr.plugin_field_key
                and db_attr.plugin_field_key not in valid_keys
            ):
                await self.session.delete(db_attr)

        await self.session.flush()

        refreshed_stmt = (
            select(MetadataCategory)
            .where(MetadataCategory.id == category.id)
            .options(selectinload(MetadataCategory.attributes))
        )
        refreshed = await self.session.execute(refreshed_stmt)
        category_loaded = refreshed.scalar_one_or_none()
        if category_loaded is None:
            raise ValueError("Failed to load metadata library category")
        return category_loaded
