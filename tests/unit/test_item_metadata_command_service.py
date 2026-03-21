from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.application.metadata import item_metadata_command_service as item_commands
from backend.db.models import Item, LinkedAccount, MetadataCategory
from backend.schemas.metadata import ItemMetadataCreate


class _Result:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


def _metadata_payload(account_id, category_id):
    return ItemMetadataCreate(
        account_id=account_id,
        item_id="item-1",
        category_id=category_id,
        values={"series": "Saga"},
    )


def _account(account_id):
    return LinkedAccount(
        id=account_id,
        provider="microsoft",
        provider_account_id="provider-account",
        email="reader@example.com",
        display_name="Reader",
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
    )


def _category(category_id, *, is_active=True):
    return MetadataCategory(
        id=category_id,
        name="Comics",
        description="Comic metadata",
        is_active=is_active,
        managed_by_plugin=False,
        plugin_key=None,
        is_locked=False,
    )


@pytest.mark.asyncio
async def test_upsert_item_metadata_validates_account_and_category_state():
    account_id = uuid4()
    category_id = uuid4()
    payload = _metadata_payload(account_id, category_id)

    missing_account_session = SimpleNamespace(get=AsyncMock(return_value=None))
    service = item_commands.ItemMetadataCommandService(missing_account_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.upsert_item_metadata(payload)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Account not found"

    missing_category_session = SimpleNamespace(
        get=AsyncMock(side_effect=[_account(account_id), None]),
    )
    service = item_commands.ItemMetadataCommandService(missing_category_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.upsert_item_metadata(payload)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Category not found"

    inactive_category_session = SimpleNamespace(
        get=AsyncMock(side_effect=[_account(account_id), _category(category_id, is_active=False)]),
    )
    service = item_commands.ItemMetadataCommandService(inactive_category_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.upsert_item_metadata(payload)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Category is inactive"


@pytest.mark.asyncio
async def test_upsert_item_metadata_syncs_missing_item_and_returns_saved_row(monkeypatch):
    account_id = uuid4()
    category_id = uuid4()
    payload = _metadata_payload(account_id, category_id)
    current_metadata = SimpleNamespace(id=uuid4(), item_id="item-1")
    modified_at = datetime(2026, 3, 10, tzinfo=UTC)
    created_at = datetime(2026, 3, 1, tzinfo=UTC)

    session = SimpleNamespace(
        get=AsyncMock(side_effect=[_account(account_id), _category(category_id)]),
        execute=AsyncMock(side_effect=[_Result(scalar=None), _Result(scalar=None), _Result(scalar=current_metadata)]),
        commit=AsyncMock(),
        add=Mock(),
    )

    apply_change_mock = AsyncMock()
    normalize_mock = Mock(return_value={"series": "Saga", "normalized": True})
    client = SimpleNamespace(
        get_item_metadata=AsyncMock(
            return_value=SimpleNamespace(
                item_type="file",
                name="Issue 001.CBZ",
                size=2048,
                modified_at=modified_at,
                created_at=created_at,
                mime_type="application/x-cbz",
            )
        ),
        get_item_path=AsyncMock(
            return_value=[
                {"id": "root", "name": "root"},
                {"id": "folder-1", "name": "Series"},
                {"id": "item-1", "name": "Issue 001.CBZ"},
            ]
        ),
    )

    monkeypatch.setattr(item_commands, "TokenManager", lambda db: "token-manager")
    monkeypatch.setattr(item_commands, "build_drive_client", lambda account, token_manager: client)
    monkeypatch.setattr(item_commands, "apply_metadata_change", apply_change_mock)
    monkeypatch.setattr(item_commands, "normalize_metadata_values", normalize_mock)

    service = item_commands.ItemMetadataCommandService(session)
    result = await service.upsert_item_metadata(payload)

    normalize_mock.assert_called_once_with({"series": "Saga"})
    apply_change_mock.assert_awaited_once()
    session.commit.assert_awaited_once()
    assert result is current_metadata

    added_item = session.add.call_args.args[0]
    assert isinstance(added_item, Item)
    assert added_item.account_id == account_id
    assert added_item.item_id == "item-1"
    assert added_item.parent_id == "folder-1"
    assert added_item.path == "/Series/Issue 001.CBZ"
    assert added_item.extension == "cbz"
    assert added_item.mime_type == "application/x-cbz"


@pytest.mark.asyncio
async def test_upsert_item_metadata_merges_existing_values_for_same_category(monkeypatch):
    account_id = uuid4()
    category_id = uuid4()
    payload = _metadata_payload(account_id, category_id)
    existing_metadata = SimpleNamespace(
        category_id=category_id,
        values={"publisher": "Dupuis", "series": "Old"},
    )
    current_metadata = SimpleNamespace(id=uuid4(), item_id="item-1")

    session = SimpleNamespace(
        get=AsyncMock(side_effect=[_account(account_id), _category(category_id)]),
        execute=AsyncMock(
            side_effect=[
                _Result(scalar=existing_metadata),
                _Result(scalar=current_metadata),
            ]
        ),
        commit=AsyncMock(),
        add=Mock(),
    )

    monkeypatch.setattr(
        item_commands.ItemMetadataCommandService,
        "_sync_item_record",
        AsyncMock(return_value=None),
    )
    apply_change_mock = AsyncMock()
    normalize_mock = Mock(side_effect=lambda values: dict(values or {}))
    monkeypatch.setattr(item_commands, "apply_metadata_change", apply_change_mock)
    monkeypatch.setattr(item_commands, "normalize_metadata_values", normalize_mock)

    service = item_commands.ItemMetadataCommandService(session)
    result = await service.upsert_item_metadata(payload)

    assert result is current_metadata
    apply_change_mock.assert_awaited_once()
    assert apply_change_mock.await_args.kwargs["values"] == {
        "publisher": "Dupuis",
        "series": "Saga",
    }


@pytest.mark.asyncio
async def test_sync_item_record_updates_existing_items_and_swallows_provider_failures(monkeypatch):
    account_id = uuid4()
    account = _account(account_id)
    existing_item = SimpleNamespace(
        name="Old name",
        size=1,
        modified_at=None,
        last_synced_at=None,
        mime_type=None,
        extension=None,
    )
    modified_at = datetime(2026, 3, 10, tzinfo=UTC)

    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Result(scalar=existing_item)),
        add=Mock(),
    )
    client = SimpleNamespace(
        get_item_metadata=AsyncMock(
            return_value=SimpleNamespace(
                item_type="file",
                name="Issue 002.pdf",
                size=8192,
                modified_at=modified_at,
                created_at=modified_at,
                mime_type="application/pdf",
            )
        ),
    )

    monkeypatch.setattr(item_commands, "TokenManager", lambda db: "token-manager")
    monkeypatch.setattr(item_commands, "build_drive_client", lambda linked_account, token_manager: client)

    service = item_commands.ItemMetadataCommandService(session)
    await service._sync_item_record(account=account, item_id="item-2")

    assert existing_item.name == "Issue 002.pdf"
    assert existing_item.size == 8192
    assert existing_item.modified_at == modified_at
    assert existing_item.mime_type == "application/pdf"
    assert existing_item.extension == "pdf"
    assert existing_item.last_synced_at is not None
    session.add.assert_not_called()

    failing_client = SimpleNamespace(get_item_metadata=AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(item_commands, "build_drive_client", lambda linked_account, token_manager: failing_client)
    await service._sync_item_record(account=account, item_id="item-3")


@pytest.mark.asyncio
async def test_upsert_item_metadata_raises_when_saved_row_cannot_be_loaded(monkeypatch):
    account_id = uuid4()
    category_id = uuid4()
    payload = _metadata_payload(account_id, category_id)

    session = SimpleNamespace(
        get=AsyncMock(side_effect=[_account(account_id), _category(category_id)]),
        execute=AsyncMock(side_effect=[_Result(scalar=None), _Result(scalar=None)]),
        commit=AsyncMock(),
        add=Mock(),
    )

    monkeypatch.setattr(
        item_commands.ItemMetadataCommandService,
        "_sync_item_record",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(item_commands, "apply_metadata_change", AsyncMock())
    monkeypatch.setattr(item_commands, "normalize_metadata_values", Mock(return_value={"series": "Saga"}))

    service = item_commands.ItemMetadataCommandService(session)
    with pytest.raises(HTTPException) as exc_info:
        await service.upsert_item_metadata(payload)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to save metadata"
