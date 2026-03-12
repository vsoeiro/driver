import io
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile

from backend.api.routes import drive as drive_routes
from backend.schemas.drive import (
    BatchDeleteRequest,
    BulkDownloadRequest,
    CopyItemRequest,
    CreateFolderRequest,
    UpdateItemRequest,
    UploadSessionRequest,
)


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


@pytest.mark.asyncio
async def test_download_zip_validates_and_builds_archive(monkeypatch, tmp_path):
    account = SimpleNamespace(id=uuid4())

    with pytest.raises(HTTPException) as empty_exc:
        await drive_routes.download_zip(
            account,
            graph_client=SimpleNamespace(),
            request=BulkDownloadRequest.model_construct(item_ids=[], archive_name=None),
        )
    assert empty_exc.value.status_code == 400

    with pytest.raises(HTTPException) as too_many_exc:
        await drive_routes.download_zip(
            account,
            graph_client=SimpleNamespace(),
            request=BulkDownloadRequest.model_construct(
                item_ids=["x"] * (drive_routes.MAX_ZIP_DOWNLOAD_ITEMS + 1),
                archive_name=None,
            ),
        )
    assert too_many_exc.value.status_code == 413

    temp_dir = tmp_path / "zip-download"
    temp_dir.mkdir()
    monkeypatch.setattr(drive_routes.tempfile, "mkdtemp", lambda: str(temp_dir))

    async def _download_to_path(account_obj, item_id, temp_file_path):
        Path(temp_file_path).write_bytes(f"bytes-{item_id}".encode())
        return "../comic.cbz"

    graph_client = SimpleNamespace(download_file_to_path=AsyncMock(side_effect=_download_to_path))
    response = await drive_routes.download_zip(
        account,
        graph_client=graph_client,
        request=BulkDownloadRequest(item_ids=["item-1", "item-2"], archive_name="../bundle"),
    )

    assert response.filename == "_bundle.zip"
    assert os.path.exists(response.path)
    with zipfile.ZipFile(response.path) as archive:
        assert sorted(archive.namelist()) == ["_comic (1).cbz", "_comic.cbz"]


@pytest.mark.asyncio
async def test_search_quota_recent_shared_and_path_routes_delegate():
    account = SimpleNamespace(id=uuid4())
    graph_client = SimpleNamespace(
        search_items=AsyncMock(return_value="search"),
        get_quota=AsyncMock(return_value={"total": 100, "used": 40, "remaining": 60, "deleted": 0}),
        get_recent_items=AsyncMock(return_value="recent"),
        get_shared_with_me=AsyncMock(return_value="shared"),
        get_item_path=AsyncMock(return_value=[{"id": "root", "name": "Root"}]),
    )

    assert await drive_routes.search_files(account, graph_client, q="Saga") == "search"
    quota = await drive_routes.get_quota(account, graph_client)
    assert quota.remaining == 60
    assert await drive_routes.get_recent_files(account, graph_client) == "recent"
    assert await drive_routes.get_shared_files(account, graph_client) == "shared"
    path = await drive_routes.get_item_path(account, graph_client, item_id="file-1")
    assert path.breadcrumb[0].name == "Root"


@pytest.mark.asyncio
async def test_upload_routes_validate_ranges_and_refresh_index(monkeypatch):
    account = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(commit=AsyncMock())
    refresh_mock = AsyncMock()
    monkeypatch.setattr(drive_routes, "_refresh_index_from_provider", refresh_mock)

    transfer_service = SimpleNamespace(upload_file_object=AsyncMock(return_value="uploaded-1"))
    monkeypatch.setattr(drive_routes, "DriveTransferService", lambda: transfer_service)
    graph_client = SimpleNamespace(
        get_item_metadata=AsyncMock(return_value=SimpleNamespace(id="uploaded-1")),
        upload_chunk=AsyncMock(return_value={"id": "uploaded-1"}),
        create_upload_session=AsyncMock(
            return_value={"upload_url": "https://upload.example/session", "expiration": "2026-03-10T12:00:00Z"}
        ),
    )

    uploaded = await drive_routes.upload_file(
        account,
        graph_client,
        db=db,
        file=UploadFile(filename="cover.png", file=io.BytesIO(b"image-bytes")),
        folder_id="root",
    )
    assert uploaded.id == "uploaded-1"
    refresh_mock.assert_awaited_once()
    db.commit.assert_awaited_once()

    oversized = UploadFile(
        filename="large.bin",
        file=io.BytesIO(b"x" * (drive_routes.MAX_SIMPLE_UPLOAD_SIZE + 1)),
    )
    with pytest.raises(HTTPException) as size_exc:
        await drive_routes.upload_file(account, graph_client, db=db, file=oversized, folder_id="root")
    assert size_exc.value.status_code == 413

    monkeypatch.setattr(
        drive_routes,
        "DriveTransferService",
        lambda: SimpleNamespace(upload_file_object=AsyncMock(side_effect=RuntimeError("boom"))),
    )
    with pytest.raises(HTTPException) as upload_exc:
        await drive_routes.upload_file(
            account,
            graph_client,
            db=db,
            file=UploadFile(filename="broken.png", file=io.BytesIO(b"123")),
            folder_id="root",
        )
    assert upload_exc.value.status_code == 500

    session_response = await drive_routes.create_upload_session(
        account,
        graph_client,
        UploadSessionRequest(
            filename="archive.cbz",
            folder_id="root",
            file_size=1024,
            conflict_behavior="rename",
        ),
    )
    assert session_response.upload_url == "https://upload.example/session"

    with pytest.raises(HTTPException):
        await drive_routes.upload_chunk(
            account,
            graph_client,
            db,
            upload_url="https://upload.example/session",
            start_byte=4,
            end_byte=3,
            total_size=10,
            file=UploadFile(filename="chunk.bin", file=io.BytesIO(b"1234")),
        )

    refresh_mock.reset_mock()
    db.commit.reset_mock()
    result = await drive_routes.upload_chunk(
        account,
        graph_client,
        db,
        upload_url="https://upload.example/session",
        start_byte=0,
        end_byte=3,
        total_size=10,
        file=UploadFile(filename="chunk.bin", file=io.BytesIO(b"1234")),
    )
    assert result == {"id": "uploaded-1"}
    refresh_mock.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_update_copy_delete_and_batch_delete_manage_index(monkeypatch):
    account = SimpleNamespace(id=uuid4())
    graph_client = SimpleNamespace(
        create_folder=AsyncMock(return_value=SimpleNamespace(id="folder-1")),
        update_item=AsyncMock(return_value=SimpleNamespace(id="folder-1", item_type="folder")),
        copy_item=AsyncMock(return_value="https://monitor.example/copy"),
        delete_item=AsyncMock(return_value=None),
        batch_delete_items=AsyncMock(return_value=None),
    )
    db = SimpleNamespace(
        commit=AsyncMock(),
        execute=AsyncMock(),
        scalar=AsyncMock(side_effect=["/Old", "/New"]),
    )
    refresh_mock = AsyncMock(return_value=SimpleNamespace(id="folder-1", item_type="folder"))
    update_descendant_paths_mock = AsyncMock()
    delete_item_and_descendants_mock = AsyncMock()
    collect_ids_mock = AsyncMock(side_effect=[["item-a", "item-b"], ["item-c"], ["item-d"]])
    monkeypatch.setattr(drive_routes, "_refresh_index_from_provider", refresh_mock)
    monkeypatch.setattr(drive_routes, "update_descendant_paths", update_descendant_paths_mock)
    monkeypatch.setattr(drive_routes, "delete_item_and_descendants", delete_item_and_descendants_mock)
    monkeypatch.setattr(drive_routes, "_collect_local_item_ids_for_deletion", collect_ids_mock)

    created = await drive_routes.create_folder(
        account,
        graph_client,
        db,
        CreateFolderRequest(name="Books", parent_folder_id="root", conflict_behavior="rename"),
    )
    assert created.id == "folder-1"

    updated = await drive_routes.update_item(
        account,
        graph_client,
        db,
        "folder-1",
        UpdateItemRequest(name="Archive", parent_folder_id="root"),
    )
    assert updated.id == "folder-1"
    update_descendant_paths_mock.assert_awaited_once_with(
        db,
        account_id=account.id,
        old_prefix="/Old",
        new_prefix="/New",
    )

    copied = await drive_routes.copy_item(
        account,
        graph_client,
        "folder-1",
        CopyItemRequest(name="Archive Copy", parent_folder_id="root"),
    )
    assert copied == {"monitor_url": "https://monitor.example/copy"}

    await drive_routes.delete_item(account, graph_client, db, "folder-1")
    delete_item_and_descendants_mock.assert_any_await(db, account_id=account.id, item_id="folder-1")

    empty_batch = BatchDeleteRequest.model_construct(item_ids=[])
    await drive_routes.batch_delete_items(account, graph_client, db, empty_batch)

    request = BatchDeleteRequest(item_ids=["folder-1", "folder-2"])
    await drive_routes.batch_delete_items(account, graph_client, db, request)

    assert collect_ids_mock.await_count == 3
    delete_calls = [call.kwargs["item_id"] for call in delete_item_and_descendants_mock.await_args_list]
    assert delete_calls[-2:] == ["folder-1", "folder-2"]
