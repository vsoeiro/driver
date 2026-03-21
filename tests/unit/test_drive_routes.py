from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.api.routes import drive as drive_routes
from backend.core.exceptions import DriveOrganizerError


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


@pytest.mark.asyncio
async def test_sanitize_zip_name_and_ensure_unique_name():
    assert drive_routes._sanitize_zip_name("../folder/file.txt") == "_folder_file.txt"

    used = set()
    assert drive_routes._ensure_unique_name("archive.zip", used) == "archive.zip"
    assert drive_routes._ensure_unique_name("archive.zip", used) == "archive (1).zip"


@pytest.mark.asyncio
async def test_collect_local_item_ids_for_deletion_uses_indexed_path(monkeypatch):
    account_id = uuid4()
    db = SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([("item-1",), ("item-2",)])))
    monkeypatch.setattr(drive_routes, "get_indexed_item_path", AsyncMock(return_value="/Books"))

    result = await drive_routes._collect_local_item_ids_for_deletion(
        db=db,
        account_id=account_id,
        item_id="folder-1",
    )

    assert result == ["item-1", "item-2"]


@pytest.mark.asyncio
async def test_refresh_index_from_provider_upserts_latest_item(monkeypatch):
    db = object()
    account = SimpleNamespace(id=uuid4())
    item = SimpleNamespace(id="file-1", name="cover.png")
    graph_client = SimpleNamespace(
        get_item_metadata=AsyncMock(return_value=item),
        get_item_path=AsyncMock(return_value=[{"id": "root", "name": "root"}]),
    )
    upsert_mock = AsyncMock()
    monkeypatch.setattr(drive_routes, "path_from_breadcrumb", lambda breadcrumb: "/Books/cover.png")
    monkeypatch.setattr(drive_routes, "parent_id_from_breadcrumb", lambda breadcrumb: "parent-1")
    monkeypatch.setattr(drive_routes, "upsert_item_record", upsert_mock)

    result = await drive_routes._refresh_index_from_provider(
        db=db,
        account=account,
        graph_client=graph_client,
        item_id="file-1",
    )

    assert result is item
    upsert_mock.assert_awaited_once_with(
        db,
        account_id=account.id,
        item_data=item,
        parent_id="parent-1",
        path="/Books/cover.png",
    )


@pytest.mark.asyncio
async def test_list_routes_delegate_to_drive_client():
    account = SimpleNamespace(id=uuid4())
    graph_client = SimpleNamespace(
        list_root_items=AsyncMock(return_value="root-items"),
        list_items_by_next_link=AsyncMock(return_value="paged-items"),
        list_folder_items=AsyncMock(return_value="folder-items"),
        get_item_metadata=AsyncMock(return_value="metadata"),
    )

    assert await drive_routes.list_root_files(account, graph_client, page_size=25, next_link=None) == "root-items"
    assert await drive_routes.list_root_files(account, graph_client, page_size=25, next_link="cursor") == "paged-items"
    assert await drive_routes.list_folder_files(account, graph_client, "folder-1", page_size=25, next_link=None) == "folder-items"
    assert await drive_routes.list_folder_files(account, graph_client, "folder-1", page_size=25, next_link="cursor") == "paged-items"
    assert await drive_routes.get_file_metadata(account, graph_client, "file-1") == "metadata"


@pytest.mark.asyncio
async def test_get_download_url_auto_resolves_other_accounts(monkeypatch):
    account = SimpleNamespace(id=uuid4())
    candidate_a = SimpleNamespace(id=uuid4())
    candidate_b = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(
        get=AsyncMock(return_value=account),
        execute=AsyncMock(return_value=_RowsResult([candidate_a, candidate_b])),
    )
    client_a = SimpleNamespace(get_download_url=AsyncMock(side_effect=DriveOrganizerError("missing", status_code=404)))
    client_b = SimpleNamespace(get_download_url=AsyncMock(return_value="https://resolved.example/file"))
    monkeypatch.setattr(drive_routes, "TokenManager", lambda db_session: object())
    monkeypatch.setattr(
        drive_routes,
        "build_drive_client",
        lambda candidate, token_manager: (
            SimpleNamespace(get_download_url=AsyncMock(side_effect=DriveOrganizerError("missing", status_code=404)))
            if candidate.id == account.id
            else client_a
            if candidate.id == candidate_a.id
            else client_b
        ),
    )

    result = await drive_routes.get_download_url(
        str(account.id),
        db,
        "file-1",
        auto_resolve_account=True,
    )

    assert result == {"download_url": "https://resolved.example/file"}


@pytest.mark.asyncio
async def test_download_content_returns_provider_bytes():
    account = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(
        get=AsyncMock(return_value=account),
        execute=AsyncMock(return_value=_RowsResult([])),
    )
    client = SimpleNamespace(download_file_bytes=AsyncMock(return_value=("cover.png", b"image-bytes")))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(drive_routes, "TokenManager", lambda db_session: object())
    monkeypatch.setattr(drive_routes, "build_drive_client", lambda linked_account, token_manager: client)

    response = await drive_routes.download_content(
        str(account.id),
        db=db,
        item_id="file-1",
    )
    monkeypatch.undo()

    assert response.media_type == "image/png"
    assert response.body == b"image-bytes"


@pytest.mark.asyncio
async def test_download_content_auto_resolves_other_accounts(monkeypatch):
    account = SimpleNamespace(id=uuid4())
    candidate = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(
        get=AsyncMock(return_value=account),
        execute=AsyncMock(return_value=_RowsResult([candidate])),
    )
    candidate_client = SimpleNamespace(
        download_file_bytes=AsyncMock(return_value=("cover.png", b"image-bytes")),
    )
    monkeypatch.setattr(drive_routes, "TokenManager", lambda db_session: object())
    monkeypatch.setattr(
        drive_routes,
        "build_drive_client",
        lambda linked_account, token_manager: (
            SimpleNamespace(download_file_bytes=AsyncMock(side_effect=DriveOrganizerError("missing", status_code=404)))
            if linked_account.id == account.id
            else candidate_client
        ),
    )

    response = await drive_routes.download_content(
        str(account.id),
        db=db,
        item_id="file-1",
        auto_resolve_account=True,
    )

    assert response.media_type == "image/png"
    assert response.body == b"image-bytes"


@pytest.mark.asyncio
async def test_download_content_auto_resolves_when_requested_account_was_deleted(monkeypatch):
    candidate = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(
        get=AsyncMock(return_value=None),
        execute=AsyncMock(return_value=_RowsResult([candidate])),
    )
    candidate_client = SimpleNamespace(
        download_file_bytes=AsyncMock(return_value=("cover.png", b"image-bytes")),
    )
    monkeypatch.setattr(drive_routes, "TokenManager", lambda db_session: object())
    monkeypatch.setattr(drive_routes, "build_drive_client", lambda linked_account, token_manager: candidate_client)

    response = await drive_routes.download_content(
        str(uuid4()),
        db=db,
        item_id="file-1",
        auto_resolve_account=True,
    )

    assert response.media_type == "image/png"
    assert response.body == b"image-bytes"
