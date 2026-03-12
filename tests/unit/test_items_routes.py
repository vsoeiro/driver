from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from backend.api.routes import items as items_routes
from backend.schemas.items import BatchMetadataUpdate


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


@pytest.mark.asyncio
async def test_list_items_delegates_to_query_service(monkeypatch):
    response = SimpleNamespace(items=[], total=0, page=1, page_size=50, total_pages=0)
    service = SimpleNamespace(list_items=AsyncMock(return_value=response))
    monkeypatch.setattr(items_routes, "ItemQueryService", lambda session: service)

    result = await items_routes.list_items(
        page=2,
        page_size=25,
        sort_by="name",
        sort_order="asc",
        metadata_sort_attribute_id="attr-1",
        metadata_sort_data_type="text",
        q="saga",
        search_fields="path",
        path_prefix="/Books",
        direct_children_only=True,
        extensions=["cbz"],
        item_type="file",
        size_min=10,
        size_max=100,
        account_id=uuid4(),
        category_id=uuid4(),
        has_metadata=True,
        metadata_filters='{"attr":"value"}',
        include_total=False,
        session=object(),
    )

    assert result is response
    service.list_items.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_similar_items_report_delegates_to_query_service(monkeypatch):
    response = SimpleNamespace(
        generated_at=datetime.now(timezone.utc),
        total_groups=0,
        total_items=0,
        page=1,
        page_size=20,
        total_pages=0,
        groups=[],
    )
    service = SimpleNamespace(get_similar_items_report=AsyncMock(return_value=response))
    monkeypatch.setattr(items_routes, "ItemQueryService", lambda session: service)

    result = await items_routes.get_similar_items_report(
        page=3,
        page_size=10,
        account_id=uuid4(),
        scope="same_account",
        sort_by="size",
        sort_order="asc",
        extensions=["png"],
        hide_low_priority=True,
        session=object(),
    )

    assert result is response
    service.get_similar_items_report.assert_awaited_once_with(
        page=3,
        page_size=10,
        account_id=service.get_similar_items_report.await_args.kwargs["account_id"],
        scope="same_account",
        sort_by="size",
        sort_order="asc",
        extensions=["png"],
        hide_low_priority=True,
    )


@pytest.mark.asyncio
async def test_batch_update_metadata_merges_existing_values(monkeypatch):
    account_id = uuid4()
    category_id = uuid4()
    existing_record = SimpleNamespace(
        item_id="item-1",
        category_id=category_id,
        values={"series": "Saga"},
    )
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[SimpleNamespace(id=account_id), SimpleNamespace(id=category_id)]),
        execute=AsyncMock(return_value=_FakeResult([existing_record])),
        commit=AsyncMock(),
    )
    apply_change = AsyncMock(side_effect=[{"changed": True}, {"changed": True}])
    monkeypatch.setattr(items_routes, "apply_metadata_change", apply_change)

    payload = BatchMetadataUpdate(
        item_ids=["item-1", "item-2"],
        account_id=account_id,
        category_id=category_id,
        values={"volume": 1},
    )

    result = await items_routes.batch_update_metadata(payload, session)

    assert result["updated"] == 1
    assert result["created"] == 1
    assert result["total"] == 2
    assert UUID(result["batch_id"])
    first_call = apply_change.await_args_list[0]
    second_call = apply_change.await_args_list[1]
    assert first_call.kwargs["values"] == {"series": "Saga", "volume": 1}
    assert second_call.kwargs["values"] == {"volume": 1}
    session.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_batch_update_metadata_raises_when_account_missing():
    payload = BatchMetadataUpdate(
        item_ids=["item-1"],
        account_id=uuid4(),
        category_id=uuid4(),
        values={"title": "Saga"},
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        await items_routes.batch_update_metadata(payload, session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Account not found"


@pytest.mark.asyncio
async def test_batch_update_metadata_raises_when_category_missing():
    payload = BatchMetadataUpdate(
        item_ids=["item-1"],
        account_id=uuid4(),
        category_id=uuid4(),
        values={"title": "Saga"},
    )
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[SimpleNamespace(id=payload.account_id), None]),
    )

    with pytest.raises(HTTPException) as exc_info:
        await items_routes.batch_update_metadata(payload, session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Category not found"
