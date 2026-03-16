from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from backend.db.models import ItemMetadata, MetadataAttribute, MetadataCategory, MetadataPlugin
from backend.services.metadata_libraries.implementations.books.schema import (
    BOOKS_LIBRARY_FIELDS,
    BOOKS_LIBRARY_KEY,
)
from backend.services.metadata_libraries.implementations.comics.schema import (
    COMICS_LIBRARY_FIELDS,
    COMICS_LIBRARY_KEY,
)
from backend.services.metadata_libraries.implementations.images.schema import (
    IMAGES_LIBRARY_FIELDS,
    IMAGES_LIBRARY_KEY,
)
from backend.services.metadata_libraries.service import MetadataLibraryService


class _Result:
    def __init__(self, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = list(scalars or [])

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._scalars))


class _FakeSession:
    def __init__(self, execute_plan=None, get_map=None):
        self.execute_plan = list(execute_plan or [])
        self.get_map = dict(get_map or {})
        self.added = []
        self.deleted = []

    async def execute(self, _stmt):
        if not self.execute_plan:
            raise AssertionError("Unexpected execute call")
        next_result = self.execute_plan.pop(0)
        if callable(next_result):
            next_result = next_result(self)
        if isinstance(next_result, Exception):
            raise next_result
        return next_result

    def add(self, instance):
        self.added.append(instance)

    async def flush(self):
        for instance in self.added:
            if isinstance(instance, MetadataCategory) and getattr(instance, "id", None) is None:
                instance.id = uuid4()
            if isinstance(instance, MetadataAttribute) and getattr(instance, "id", None) is None:
                instance.id = uuid4()

    async def get(self, model, key):
        return self.get_map.get((model, key))

    async def delete(self, instance):
        self.deleted.append(instance)


def _plugin(key, *, is_active=False, category_id=None):
    return MetadataPlugin(
        key=key,
        name=f"{key} name",
        description=f"{key} description",
        is_active=is_active,
        category_id=category_id,
        created_at=datetime(2026, 3, 10, tzinfo=UTC),
        updated_at=datetime(2026, 3, 10, tzinfo=UTC),
    )


def _category(category_id, *, name, plugin_key=None, is_active=False, managed=True):
    category = MetadataCategory(
        id=category_id,
        name=name,
        description=f"{name} description",
        is_active=is_active,
        managed_by_plugin=managed,
        plugin_key=plugin_key,
        is_locked=False,
    )
    category.attributes = []
    return category


@pytest.mark.asyncio
async def test_list_libraries_returns_empty_when_plugins_table_is_missing():
    session = _FakeSession(
        execute_plan=[
            OperationalError("select", {}, Exception("no such table: metadata_plugins")),
        ]
    )

    service = MetadataLibraryService(session)
    assert await service.list_libraries() == []


@pytest.mark.asyncio
async def test_activate_images_library_creates_library_category_and_attributes():
    def _loaded_images_category(session):
        category = next(
            instance
            for instance in session.added
            if isinstance(instance, MetadataCategory) and instance.plugin_key == IMAGES_LIBRARY_KEY
        )
        category.attributes = [
            instance
            for instance in session.added
            if isinstance(instance, MetadataAttribute) and instance.category_id == category.id
        ]
        return _Result(scalar=category)

    session = _FakeSession(
        execute_plan=[
            _Result(scalar=None),
            _Result(scalar=None),
            _Result(scalar=None),
            _Result(scalars=[]),
            _loaded_images_category,
        ]
    )

    service = MetadataLibraryService(session)
    library = await service.activate_images_library()

    assert library.is_active is True
    assert library.category_id is not None

    created_category = next(
        instance
        for instance in session.added
        if isinstance(instance, MetadataCategory) and instance.plugin_key == IMAGES_LIBRARY_KEY
    )
    created_attributes = [
        instance
        for instance in session.added
        if isinstance(instance, MetadataAttribute) and instance.category_id == created_category.id
    ]
    assert created_category.is_active is True
    assert created_category.is_locked is True
    assert len(created_attributes) == len(IMAGES_LIBRARY_FIELDS)
    assert all(attr.plugin_key == IMAGES_LIBRARY_KEY for attr in created_attributes)


@pytest.mark.asyncio
async def test_ensure_comics_category_updates_existing_fields_and_removes_stale_ones():
    category = _category(uuid4(), name="Comics", plugin_key=COMICS_LIBRARY_KEY, is_active=False)
    spec = COMICS_LIBRARY_FIELDS[0]
    existing_attr = MetadataAttribute(
        id=uuid4(),
        category_id=category.id,
        name="Old name",
        data_type="text",
        options=None,
        is_required=False,
        managed_by_plugin=False,
        plugin_key=None,
        plugin_field_key=spec.key,
        is_locked=False,
    )
    stale_attr = MetadataAttribute(
        id=uuid4(),
        category_id=category.id,
        name="Obsolete",
        data_type="text",
        options=None,
        is_required=False,
        managed_by_plugin=True,
        plugin_key=COMICS_LIBRARY_KEY,
        plugin_field_key="obsolete",
        is_locked=False,
    )

    def _refreshed_category(session):
        category.attributes = [
            existing_attr,
            *[
                instance
                for instance in session.added
                if isinstance(instance, MetadataAttribute) and instance.category_id == category.id
            ],
        ]
        return _Result(scalar=category)

    session = _FakeSession(
        execute_plan=[
            _Result(scalar=category),
            _Result(scalars=[existing_attr, stale_attr]),
            _Result(scalars=[]),
            _refreshed_category,
        ]
    )

    service = MetadataLibraryService(session)
    loaded_category = await service._ensure_comics_category()

    assert loaded_category is category
    assert category.is_active is True
    assert category.managed_by_plugin is True
    assert category.is_locked is True
    assert existing_attr.name == spec.name
    assert existing_attr.data_type == spec.data_type
    assert existing_attr.plugin_key == COMICS_LIBRARY_KEY
    assert stale_attr in session.deleted

    created_attributes = [
        instance
        for instance in session.added
        if isinstance(instance, MetadataAttribute) and instance.category_id == category.id
    ]
    assert created_attributes


@pytest.mark.asyncio
async def test_ensure_comics_category_migrates_existing_creator_values_to_tags():
    category = _category(uuid4(), name="Comics", plugin_key=COMICS_LIBRARY_KEY, is_active=True)
    writer_spec = next(spec for spec in COMICS_LIBRARY_FIELDS if spec.key == "writer")
    writer_attr = MetadataAttribute(
        id=uuid4(),
        category_id=category.id,
        name="Writer",
        data_type="text",
        options=None,
        is_required=False,
        managed_by_plugin=True,
        plugin_key=COMICS_LIBRARY_KEY,
        plugin_field_key="writer",
        is_locked=True,
    )
    metadata_row = ItemMetadata(
        id=uuid4(),
        account_id=uuid4(),
        item_id="item-1",
        category_id=category.id,
        values={
            str(writer_attr.id): "Alan Moore, Dave Gibbons, alan moore",
        },
        version=1,
    )

    def _refreshed_category(_session):
        category.attributes = [writer_attr]
        return _Result(scalar=category)

    session = _FakeSession(
        execute_plan=[
            _Result(scalar=category),
            _Result(scalars=[writer_attr]),
            _Result(scalars=[metadata_row]),
            _refreshed_category,
        ]
    )

    service = MetadataLibraryService(session)
    loaded_category = await service._ensure_comics_category()

    assert loaded_category is category
    assert writer_attr.data_type == writer_spec.data_type == "tags"
    assert metadata_row.values[str(writer_attr.id)] == ["Alan Moore", "Dave Gibbons"]


@pytest.mark.asyncio
async def test_deactivate_books_library_disables_the_linked_category():
    category = _category(uuid4(), name="Books", plugin_key=BOOKS_LIBRARY_KEY, is_active=True)
    library = _plugin(BOOKS_LIBRARY_KEY, is_active=True, category_id=category.id)
    session = _FakeSession(
        execute_plan=[_Result(scalar=library)],
        get_map={(MetadataCategory, category.id): category},
    )

    service = MetadataLibraryService(session)
    result = await service.deactivate_books_library()

    assert result is library
    assert library.is_active is False
    assert category.is_active is False


@pytest.mark.asyncio
async def test_attribute_maps_return_plugin_field_ids_for_active_books_category():
    category = _category(uuid4(), name="Books", plugin_key=BOOKS_LIBRARY_KEY, is_active=True)
    category.attributes = [
        MetadataAttribute(
            id=uuid4(),
            category_id=category.id,
            name=BOOKS_LIBRARY_FIELDS[0].name,
            data_type=BOOKS_LIBRARY_FIELDS[0].data_type,
            options=None,
            is_required=BOOKS_LIBRARY_FIELDS[0].is_required,
            managed_by_plugin=True,
            plugin_key=BOOKS_LIBRARY_KEY,
            plugin_field_key=BOOKS_LIBRARY_FIELDS[0].key,
            is_locked=True,
        ),
        MetadataAttribute(
            id=uuid4(),
            category_id=category.id,
            name="Ignored",
            data_type="text",
            options=None,
            is_required=False,
            managed_by_plugin=True,
            plugin_key=BOOKS_LIBRARY_KEY,
            plugin_field_key=None,
            is_locked=True,
        ),
    ]

    service = MetadataLibraryService(_FakeSession())
    service.ensure_active_books_category = AsyncMock(return_value=category)

    mapping = await service.books_attribute_id_map()

    assert mapping == {BOOKS_LIBRARY_FIELDS[0].key: str(category.attributes[0].id)}
