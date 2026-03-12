from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from backend.api.routes import metadata_impl as metadata_routes
from backend.domain.errors import NotFoundError
from backend.schemas.metadata import (
    ItemMetadataFieldUpdateRequest,
    MetadataAttributeCreate,
    MetadataAttributeUpdate,
    MetadataCategoryCreate,
    MetadataFormLayoutUpdate,
    MetadataRuleCreate,
    MetadataRulePreviewRequest,
    MetadataRuleUpdate,
)


class _Result:
    def __init__(self, scalar=None, scalars=None, rows=None):
        self._scalar = scalar
        self._scalars = list(scalars or [])
        self._rows = list(rows or [])

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._scalars))

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


def _attribute(**overrides):
    payload = {
        "id": uuid4(),
        "category_id": uuid4(),
        "name": "Field",
        "data_type": "text",
        "options": None,
        "is_required": False,
        "is_locked": False,
        "managed_by_plugin": False,
        "plugin_key": None,
        "plugin_field_key": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _rule_payload(target_category_id):
    return MetadataRuleCreate(
        name="Auto classify",
        target_category_id=target_category_id,
        target_values={"series": "Saga"},
    )


def test_layout_helpers_normalize_payload_and_form_response():
    category_id = uuid4()
    attr_one = uuid4()
    attr_two = uuid4()

    assert metadata_routes._to_int("5", 0) == 5
    assert metadata_routes._to_int("oops", 3) == 3
    assert metadata_routes._clamp(50, 1, 24) == 24
    assert metadata_routes._to_bool("yes") is True
    assert metadata_routes._to_bool("off") is False
    assert metadata_routes._layout_item_key({"item_type": "section", "item_id": "hero"}) == "section:hero"

    occupied = set()
    assert metadata_routes._region_is_free(occupied, 0, 0, 2) is True
    metadata_routes._occupy_region(occupied, 0, 0, 2)
    assert metadata_routes._region_is_free(occupied, 0, 0, 2) is False
    assert metadata_routes._find_first_free_slot(occupied, 3, 2, 0) == (0, 1)

    legacy = metadata_routes._build_legacy_layout_items(
        {
            "ordered_attribute_ids": [str(attr_one), "invalid", str(attr_two)],
            "half_width_attribute_ids": [str(attr_one)],
        },
        4,
    )
    assert legacy[0]["w"] == 2
    assert legacy[1]["y"] == 1

    normalized = metadata_routes._normalize_layout_payload(
        {
            "columns": "30",
            "row_height": "4",
            "hide_read_only_fields": "yes",
            "items": [
                {"item_type": "section", "item_id": "hero", "title": "Hero section", "y": 0},
                {"item_type": "section", "item_id": "hero", "title": "duplicate", "y": 2},
                {
                    "item_type": "attribute",
                    "attribute_id": str(attr_one),
                    "x": 0,
                    "y": 0,
                    "w": 12,
                },
                {
                    "item_type": "attribute",
                    "attribute_id": str(attr_one),
                    "x": 5,
                    "y": 0,
                    "w": 12,
                },
                {
                    "item_type": "attribute",
                    "attribute_id": str(attr_two),
                    "x": 20,
                    "y": 0,
                    "w": 12,
                },
                {"item_type": "attribute", "attribute_id": "not-a-uuid"},
            ],
        },
        valid_attr_ids={str(attr_one), str(attr_two)},
        ordered_attr_ids=[str(attr_one), str(attr_two)],
    )

    assert normalized["columns"] == 24
    assert normalized["row_height"] == 4
    assert normalized["hide_read_only_fields"] is True
    assert [item["item_type"] for item in normalized["items"]] == ["section", "attribute", "attribute"]
    assert normalized["ordered_attribute_ids"] == [str(attr_one), str(attr_two)]
    assert normalized["half_width_attribute_ids"] == [str(attr_one), str(attr_two)]

    response = metadata_routes._to_form_layout_response(category_id, normalized)
    assert response.category_id == category_id
    assert len(response.items) == 3
    assert response.ordered_attribute_ids == [attr_one, attr_two]


@pytest.mark.asyncio
async def test_load_and_save_form_layout_helpers():
    empty_session = SimpleNamespace(get=AsyncMock(return_value=None), add=Mock(), commit=AsyncMock())
    assert await metadata_routes._load_form_layouts(empty_session) == {}

    invalid_session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(value="{invalid json")),
    )
    assert await metadata_routes._load_form_layouts(invalid_session) == {}

    valid_session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(value='{"cat": {"columns": 12}}')),
    )
    assert await metadata_routes._load_form_layouts(valid_session) == {"cat": {"columns": 12}}

    await metadata_routes._save_form_layouts(empty_session, {"cat": {"columns": 12}})
    empty_session.add.assert_called_once()
    empty_session.commit.assert_awaited_once()

    existing_row = SimpleNamespace(value="{}", description=None)
    update_session = SimpleNamespace(get=AsyncMock(return_value=existing_row), add=Mock(), commit=AsyncMock())
    await metadata_routes._save_form_layouts(update_session, {"cat": {"columns": 6}})
    assert '"columns": 6' in existing_row.value
    update_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_and_get_metadata_form_layouts(monkeypatch):
    category_id = uuid4()
    attr_one = uuid4()
    attr_two = uuid4()
    load_mock = AsyncMock(
        return_value={
            "bad-category-id": {"columns": 6},
            str(category_id): {
                "columns": 12,
                "ordered_attribute_ids": [str(attr_one)],
                "half_width_attribute_ids": [str(attr_one)],
            },
        }
    )
    monkeypatch.setattr(metadata_routes, "_load_form_layouts", load_mock)

    layouts = await metadata_routes.list_metadata_form_layouts(session=object())
    assert len(layouts) == 1
    assert layouts[0].category_id == category_id

    session = SimpleNamespace(execute=AsyncMock(return_value=_Result(scalars=[attr_one, attr_two])))
    layout = await metadata_routes.get_metadata_form_layout(category_id, session=session)
    assert layout.category_id == category_id
    assert layout.ordered_attribute_ids == [attr_one, attr_two]


@pytest.mark.asyncio
async def test_upsert_metadata_form_layout_validates_category_and_saves(monkeypatch):
    category_id = uuid4()
    attr_id = uuid4()
    payload = MetadataFormLayoutUpdate(
        columns=12,
        items=[
            {
                "item_type": "attribute",
                "attribute_id": attr_id,
                "x": 0,
                "y": 0,
                "w": 6,
                "h": 1,
            }
        ],
        ordered_attribute_ids=[attr_id],
    )

    missing_session = SimpleNamespace(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.upsert_metadata_form_layout(category_id, payload, session=missing_session)
    assert exc_info.value.status_code == 404

    save_mock = AsyncMock()
    monkeypatch.setattr(metadata_routes, "_load_form_layouts", AsyncMock(return_value={}))
    monkeypatch.setattr(metadata_routes, "_save_form_layouts", save_mock)
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(id=category_id)),
        execute=AsyncMock(return_value=_Result(scalars=[attr_id])),
    )

    response = await metadata_routes.upsert_metadata_form_layout(category_id, payload, session=session)

    saved_layouts = save_mock.await_args.args[1]
    assert str(category_id) in saved_layouts
    assert saved_layouts[str(category_id)]["ordered_attribute_ids"] == [str(attr_id)]
    assert response.category_id == category_id
    assert response.ordered_attribute_ids == [attr_id]


@pytest.mark.asyncio
async def test_category_and_attribute_routes_validate_state():
    duplicate_session = SimpleNamespace(execute=AsyncMock(return_value=_Result(scalar=object())))
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.create_category(
            MetadataCategoryCreate(name="Comics", description="Books"),
            session=duplicate_session,
        )
    assert exc_info.value.status_code == 400

    created_at = datetime(2026, 3, 10, tzinfo=UTC)

    async def _refresh_category(category):
        category.id = uuid4()
        category.created_at = created_at

    create_session = SimpleNamespace(
        execute=AsyncMock(return_value=_Result(scalar=None)),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(side_effect=_refresh_category),
    )
    category = await metadata_routes.create_category(
        MetadataCategoryCreate(name="Images", description="Pictures"),
        session=create_session,
    )
    assert category.name == "Images"
    assert category.created_at == created_at

    inactive_session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(is_active=False)))
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.create_attribute(
            uuid4(),
            MetadataAttributeCreate(name="Label", data_type="text"),
            session=inactive_session,
        )
    assert exc_info.value.status_code == 400

    active_session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(is_active=True)),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    created = await metadata_routes.create_attribute(
        uuid4(),
        MetadataAttributeCreate(name="Label", data_type="text"),
        session=active_session,
    )
    assert created.name == "Label"

    attribute_id = uuid4()
    db_attribute = _attribute(
        id=attribute_id,
        name="Status",
        data_type="select",
        options={"options": ["New", "Done"]},
    )
    update_session = SimpleNamespace(
        get=AsyncMock(return_value=db_attribute),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    updated = await metadata_routes.update_attribute(
        attribute_id,
        MetadataAttributeUpdate(name="Status", data_type="text", options={"options": ["ignored"]}),
        session=update_session,
    )
    assert updated.data_type == "text"
    assert updated.options is None

    locked_session = SimpleNamespace(
        get=AsyncMock(return_value=_attribute(is_locked=True)),
    )
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.delete_attribute(uuid4(), session=locked_session)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_item_metadata_routes_handle_conflicts_and_updates(monkeypatch):
    account_id = uuid4()
    category_id = uuid4()
    attribute_id = uuid4()
    attribute = _attribute(id=attribute_id, category_id=category_id)

    conflict_session = SimpleNamespace(
        get=AsyncMock(return_value=attribute),
        execute=AsyncMock(return_value=_Result(scalar=SimpleNamespace(version=4, category_id=category_id, values={}))),
    )
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.update_item_metadata_attribute(
            account_id,
            "item-1",
            attribute_id,
            ItemMetadataFieldUpdateRequest(value="new", category_id=category_id, expected_version=3),
            session=conflict_session,
        )
    assert exc_info.value.status_code == 409

    apply_mock = AsyncMock()
    monkeypatch.setattr(metadata_routes, "apply_metadata_change", apply_mock)
    existing = SimpleNamespace(
        account_id=account_id,
        item_id="item-1",
        category_id=category_id,
        version=2,
        values={str(attribute_id): "old", "keep": "value"},
    )
    updated_row = SimpleNamespace(
        account_id=account_id,
        item_id="item-1",
        category_id=category_id,
        version=3,
        values={"keep": "value"},
    )
    update_session = SimpleNamespace(
        get=AsyncMock(return_value=attribute),
        execute=AsyncMock(side_effect=[_Result(scalar=existing), _Result(scalar=updated_row)]),
        commit=AsyncMock(),
    )

    updated = await metadata_routes.update_item_metadata_attribute(
        account_id,
        "item-1",
        attribute_id,
        ItemMetadataFieldUpdateRequest(value=None, category_id=category_id, expected_version=2),
        session=update_session,
    )

    assert updated is updated_row
    apply_mock.assert_awaited_once_with(
        update_session,
        account_id=account_id,
        item_id="item-1",
        category_id=category_id,
        values={"keep": "value"},
    )

    mismatch_session = SimpleNamespace(
        get=AsyncMock(return_value=attribute),
        execute=AsyncMock(return_value=_Result(scalar=None)),
    )
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.update_item_metadata_attribute(
            account_id,
            "item-1",
            attribute_id,
            ItemMetadataFieldUpdateRequest(value="x", category_id=uuid4()),
            session=mismatch_session,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_batch_history_and_undo_metadata_routes(monkeypatch):
    account_id = uuid4()
    batch_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    apply_mock = AsyncMock()
    undo_mock = AsyncMock(return_value={"restored": 2})
    monkeypatch.setattr(metadata_routes, "apply_metadata_change", apply_mock)
    monkeypatch.setattr(metadata_routes, "undo_metadata_batch", undo_mock)
    monkeypatch.setattr(metadata_routes.uuid, "uuid4", lambda: batch_id)

    missing_delete_session = SimpleNamespace(execute=AsyncMock(return_value=_Result(scalar=None)))
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.delete_item_metadata(account_id, "item-missing", session=missing_delete_session)
    assert exc_info.value.status_code == 404

    delete_session = SimpleNamespace(
        execute=AsyncMock(return_value=_Result(scalar=SimpleNamespace(account_id=account_id, item_id="item-1"))),
        commit=AsyncMock(),
    )
    await metadata_routes.delete_item_metadata(account_id, "item-1", session=delete_session)
    apply_mock.assert_any_await(
        delete_session,
        account_id=account_id,
        item_id="item-1",
        category_id=None,
        values=None,
    )

    metadata_rows = [
        SimpleNamespace(account_id=account_id, item_id="item-1"),
        SimpleNamespace(account_id=account_id, item_id="item-2"),
    ]
    batch_session = SimpleNamespace(
        execute=AsyncMock(return_value=_Result(scalars=metadata_rows)),
        commit=AsyncMock(),
    )
    await metadata_routes.batch_delete_item_metadata(account_id, ["item-1", "item-2"], session=batch_session)
    assert apply_mock.await_count == 3
    batch_calls = [call.kwargs["batch_id"] for call in apply_mock.await_args_list[1:]]
    assert batch_calls == [batch_id, batch_id]

    history_rows = [SimpleNamespace(id=uuid4(), action="updated")]
    history_session = SimpleNamespace(execute=AsyncMock(return_value=_Result(scalars=history_rows)))
    assert await metadata_routes.get_item_metadata_history(account_id, "item-1", session=history_session) == history_rows

    undo_session = SimpleNamespace(commit=AsyncMock())
    result = await metadata_routes.undo_metadata_batch_route(batch_id, session=undo_session)
    assert result == {"batch_id": str(batch_id), "restored": 2}


@pytest.mark.asyncio
async def test_series_rules_and_library_routes_delegate(monkeypatch):
    category_id = uuid4()
    preview_request = MetadataRulePreviewRequest(
        target_category_id=category_id,
        target_values={"series": "Saga"},
    )
    rules_service = SimpleNamespace(
        list_rules=AsyncMock(return_value=["rule-1"]),
        create_rule=AsyncMock(return_value="created"),
        update_rule=AsyncMock(return_value="updated"),
        delete_rule=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(metadata_routes, "MetadataRulesService", lambda session: rules_service)
    monkeypatch.setattr(metadata_routes, "_validate_rule_configuration", AsyncMock())
    preview_service = SimpleNamespace(preview=AsyncMock(return_value={"total_matches": 1}))
    monkeypatch.setattr(metadata_routes, "RulePreviewService", lambda session: preview_service)
    libraries_service = SimpleNamespace(list_libraries=AsyncMock(return_value=["library-1"]))
    monkeypatch.setattr(metadata_routes, "MetadataLibraryService", lambda session: libraries_service)

    assert await metadata_routes.list_metadata_rules(session=object()) == ["rule-1"]
    assert await metadata_routes.create_metadata_rule(_rule_payload(category_id), session=object()) == "created"
    assert await metadata_routes.update_metadata_rule(uuid4(), MetadataRuleUpdate(name="Updated"), session=object()) == "updated"
    assert await metadata_routes.delete_metadata_rule(uuid4(), session=object()) is None
    assert await metadata_routes.preview_metadata_rule(preview_request, session=object()) == {"total_matches": 1}
    assert await metadata_routes.list_metadata_libraries(session=object()) == ["library-1"]

    series_service = SimpleNamespace(
        get_category_series_summary=AsyncMock(return_value={"rows": [], "total": 0, "page": 1, "page_size": 50, "total_pages": 0})
    )
    monkeypatch.setattr(metadata_routes, "SeriesQueryService", lambda session: series_service)
    result = await metadata_routes.get_category_series_summary(category_id, session=object())
    assert result["page"] == 1

    failing_series = SimpleNamespace(
        get_category_series_summary=AsyncMock(side_effect=NotFoundError("missing category"))
    )
    monkeypatch.setattr(metadata_routes, "SeriesQueryService", lambda session: failing_series)
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.get_category_series_summary(category_id, session=object())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_activate_and_deactivate_library_routes_map_errors(monkeypatch):
    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock(), rollback=AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.activate_metadata_library("unknown", session=session)
    assert exc_info.value.status_code == 404

    failing_service = SimpleNamespace(
        activate_comics_library=AsyncMock(side_effect=ValueError("bad config")),
    )
    monkeypatch.setattr(metadata_routes, "MetadataLibraryService", lambda db: failing_service)
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.activate_metadata_library(metadata_routes.COMICS_LIBRARY_KEY, session=session)
    assert exc_info.value.status_code == 400
    session.rollback.assert_awaited()

    migration_error = OperationalError(
        "select 1",
        {},
        Exception("no such table: metadata_plugins"),
    )
    broken_service = SimpleNamespace(
        activate_images_library=AsyncMock(side_effect=migration_error),
    )
    monkeypatch.setattr(metadata_routes, "MetadataLibraryService", lambda db: broken_service)
    with pytest.raises(HTTPException) as exc_info:
        await metadata_routes.activate_metadata_library(metadata_routes.IMAGES_LIBRARY_KEY, session=session)
    assert exc_info.value.status_code == 409

    library = SimpleNamespace(key=metadata_routes.BOOKS_LIBRARY_KEY)
    success_service = SimpleNamespace(
        activate_books_library=AsyncMock(return_value=library),
        deactivate_books_library=AsyncMock(return_value=library),
    )
    monkeypatch.setattr(metadata_routes, "MetadataLibraryService", lambda db: success_service)
    assert await metadata_routes.activate_metadata_library(metadata_routes.BOOKS_LIBRARY_KEY, session=session) is library
    assert await metadata_routes.deactivate_metadata_library(metadata_routes.BOOKS_LIBRARY_KEY, session=session) is library
