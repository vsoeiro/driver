from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.core.exceptions import DriveOrganizerError
from backend.services.metadata_libraries.comics import metadata_service as comics_metadata
from backend.services.metadata_libraries.books.metadata_service import (
    BookMetadataService,
)
from backend.services.metadata_libraries.comics.metadata_service import (
    ComicMetadataService,
)


@pytest.mark.asyncio
async def test_comic_ensure_cover_folder_follows_pagination_before_creating():
    session = AsyncMock()
    service = ComicMetadataService(session)
    account = SimpleNamespace(id="account-1")
    client = AsyncMock()
    client.list_root_items = AsyncMock(
        return_value=SimpleNamespace(
            items=[SimpleNamespace(item_type="folder", name="Other", id="other")],
            next_link="page-2",
        )
    )
    client.list_items_by_next_link = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                SimpleNamespace(
                    item_type="folder",
                    name="__driver_comic_covers__",
                    id="covers-123",
                )
            ],
            next_link=None,
        )
    )

    folder_id = await service._ensure_cover_folder(
        client,
        account,
        parent_folder_id="root",
        cover_folder_name="__driver_comic_covers__",
    )

    assert folder_id == "covers-123"
    client.create_folder.assert_not_awaited()


@pytest.mark.asyncio
async def test_book_ensure_cover_folder_follows_pagination_before_creating():
    session = AsyncMock()
    service = BookMetadataService(session)
    account = SimpleNamespace(id="account-1")
    client = AsyncMock()
    client.list_folder_items = AsyncMock(
        return_value=SimpleNamespace(
            items=[SimpleNamespace(item_type="folder", name="Other", id="other")],
            next_link="page-2",
        )
    )
    client.list_items_by_next_link = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                SimpleNamespace(
                    item_type="folder",
                    name="__driver_comic_covers__",
                    id="covers-456",
                )
            ],
            next_link=None,
        )
    )

    folder_id = await service._ensure_cover_folder(
        client,
        account,
        parent_folder_id="parent-1",
        cover_folder_name="__driver_comic_covers__",
    )

    assert folder_id == "covers-456"
    client.create_folder.assert_not_awaited()


@pytest.mark.asyncio
async def test_comic_resolve_cover_folder_id_recreates_and_persists_when_saved_folder_is_missing(monkeypatch):
    session = AsyncMock()
    service = comics_metadata.ComicMetadataService(session)
    account = SimpleNamespace(id="acc-1")
    client = AsyncMock()
    client.get_item_metadata = AsyncMock(
        side_effect=DriveOrganizerError("missing", status_code=404)
    )
    ensure_cover_folder = AsyncMock(return_value="covers-new")
    persist_folder_id = AsyncMock()
    monkeypatch.setattr(service, "_ensure_cover_folder", ensure_cover_folder)
    monkeypatch.setattr(
        comics_metadata,
        "MetadataLibrarySettingsService",
        lambda session: SimpleNamespace(
            persist_cover_storage_folder_id=persist_folder_id
        ),
    )

    folder_id = await service._resolve_cover_folder_id(
        client=client,
        account=account,
        plugin_settings=SimpleNamespace(
            storage_folder_id="covers-old",
            storage_account_id="acc-1",
            storage_parent_folder_id="root",
            storage_folder_name="__driver_comic_covers__",
        ),
    )

    assert folder_id == "covers-new"
    ensure_cover_folder.assert_awaited_once()
    persist_folder_id.assert_awaited_once_with(
        "comics_core",
        folder_id="covers-new",
    )
