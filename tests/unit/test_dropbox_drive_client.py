from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.core.exceptions import DriveOrganizerError
from backend.services.dropbox.drive import client as dropbox_module
from backend.services.dropbox.drive.client import (
    _DROPBOX_UPLOAD_SESSIONS,
    DROPBOX_CONTENT_BASE_URL,
    DropboxDriveClient,
    _clear_session_payload,
    _extract_session_key,
    _session_payload_from_url,
    _session_payload_to_url,
)


def _account():
    return SimpleNamespace(id="acc-1", provider="dropbox")


def _response(status_code: int, *, json_body=None, text: str = "", headers=None):
    request = httpx.Request("POST", "https://dropbox.test")
    kwargs = {"headers": headers or {}}
    if json_body is not None:
        kwargs["json"] = json_body
    else:
        kwargs["content"] = text.encode()
    return httpx.Response(status_code, request=request, **kwargs)


class _FakeHttpClient:
    def __init__(self, *, responses=None, error=None):
        self._responses = list(responses or [])
        self.error = error
        self.calls = []

    async def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self._responses.pop(0)


def test_dropbox_session_helpers_and_parsers(monkeypatch):
    _DROPBOX_UPLOAD_SESSIONS.clear()
    now = datetime.now(UTC)
    expired_at = now - timedelta(seconds=1)
    _DROPBOX_UPLOAD_SESSIONS["expired"] = {"expires_at": expired_at}

    upload_url, expires_at = _session_payload_to_url({"provider": "dropbox", "session_id": "session-1"})
    payload = _session_payload_from_url(upload_url)
    client = DropboxDriveClient(SimpleNamespace())
    folder = client._parse_single_item({
        ".tag": "folder",
        "id": "folder-1",
        "name": "Folder",
        "size": 999,
    })
    file_item = client._parse_single_item({
        ".tag": "file",
        "id": "file-1",
        "name": "Comic.cbz",
        "size": "2048",
        "content_hash": "hash",
        "client_modified": "2026-03-11T12:00:00Z",
    })
    listing = client._parse_list(
        {
            "entries": [{"id": "file-1", "name": "Comic.cbz", ".tag": "file"}],
            "cursor": "cursor-1",
            "has_more": True,
        },
        "/comics",
    )

    assert upload_url.startswith("dropbox-session://")
    assert expires_at > now
    assert "expired" not in _DROPBOX_UPLOAD_SESSIONS
    assert payload["session_id"] == "session-1"
    assert _extract_session_key(upload_url)
    assert client._normalize_path("folder") == "/folder"
    assert client._normalize_path("/") == ""
    assert folder.item_type == "folder"
    assert folder.size == 0
    assert file_item.mime_type == "hash"
    assert listing.next_link == "dropbox:cursor:cursor-1"

    _clear_session_payload(upload_url)
    with pytest.raises(DriveOrganizerError, match="Invalid or expired"):
        _session_payload_from_url(upload_url)


@pytest.mark.asyncio
async def test_request_helpers_cover_success_and_errors():
    client = DropboxDriveClient(SimpleNamespace())
    account = _account()
    client._perform_oauth_request = AsyncMock(side_effect=[
        _response(200, json_body={"ok": True}),
        _response(204, text=""),
        _response(200, text="payload", headers={"Dropbox-API-Result": "{\"name\":\"Comic.cbz\"}"}),
        _response(200, json_body={"id": "upload-1"}),
        _response(400, json_body={"error": {"message": "denied"}}),
        _response(400, text="download failed"),
        _response(500, text="upload failed"),
    ])

    rpc = await client._request_rpc("/files/list_folder", account, payload={"path": ""})
    empty = await client._request_rpc("/files/delete_v2", account, payload={"path": "/file"})
    metadata, content = await client._request_content_download(
        "/files/download",
        account,
        payload={"path": "/Comic.cbz"},
    )
    uploaded = await client._request_content_upload(
        "/files/upload",
        account,
        arg_payload={"path": "/Comic.cbz"},
        content=b"123",
    )

    with pytest.raises(DriveOrganizerError, match="Dropbox API error: denied"):
        await client._request_rpc("/files/list_folder", account, payload={"path": ""})
    with pytest.raises(DriveOrganizerError, match="Dropbox API error: download failed"):
        await client._request_content_download("/files/download", account, payload={"path": "/Comic.cbz"})
    with pytest.raises(DriveOrganizerError, match="Dropbox API error: upload failed"):
        await client._request_content_upload(
            "/files/upload",
            account,
            arg_payload={"path": "/Comic.cbz"},
            content=b"123",
        )

    assert rpc == {"ok": True}
    assert empty == {}
    assert metadata["name"] == "Comic.cbz"
    assert content == b"payload"
    assert uploaded == {"id": "upload-1"}


@pytest.mark.asyncio
async def test_listing_metadata_search_quota_recent_shared_and_path_helpers():
    client = DropboxDriveClient(SimpleNamespace())
    account = _account()
    client._request_rpc = AsyncMock(side_effect=[
        {"entries": [{"id": "root-file", "name": "Root.cbz", ".tag": "file"}]},
        {"path_display": "/Comics", ".tag": "folder"},
        {"entries": [{"id": "child-file", "name": "Child.cbz", ".tag": "file"}]},
        {"entries": [{"id": "paged-file", "name": "Paged.cbz", ".tag": "file"}]},
        {"id": "id:meta-1", "name": "Meta.cbz", ".tag": "file"},
        {"link": "https://dropbox.test/download"},
        {
            "matches": [
                {"metadata": {"metadata": {"id": "search-1", "name": "Query.cbz", ".tag": "file"}}}
            ]
        },
        {"used": 123, "allocation": {".tag": "individual", "allocated": 500}},
        {"path_display": "/Library/Comic.cbz", "name": "Comic.cbz", "id": "id:file-1"},
        {"id": "id:folder-1", "name": "Library", ".tag": "folder"},
        {"id": "id:file-1", "name": "Comic.cbz", ".tag": "file"},
        {
            "entries": [
                {"id": "old", "name": "Old.cbz", ".tag": "file", "server_modified": "2026-03-10T10:00:00Z"},
                {"id": "new", "name": "New.cbz", ".tag": "file", "server_modified": "2026-03-11T10:00:00Z"},
            ]
        },
        {"entries": [{"file_metadata": {"id": "shared-1", "name": "Shared.cbz", ".tag": "file"}}]},
    ])

    root = await client.list_root_items(account, page_size=500)
    folder = await client.list_folder_items(account, "/Comics", page_size=0)
    paged = await client.list_items_by_next_link(account, "dropbox:cursor:cursor-1")
    metadata = await client.get_item_metadata(account, "id:meta-1")
    download_url = await client.get_download_url(account, "id:meta-1")
    search = await client.search_items(account, "Dylan Dog")
    quota = await client.get_quota(account)
    breadcrumb = await client.get_item_path(account, "id:file-1")
    recent = await client.get_recent_items(account)
    shared = await client.get_shared_with_me(account)

    assert root.items[0].id == "root-file"
    assert folder.folder_path == "/Comics"
    assert paged.items[0].id == "paged-file"
    assert metadata.id == "id:meta-1"
    assert download_url == "https://dropbox.test/download"
    assert search.items[0].id == "search-1"
    assert quota == {"total": 500, "used": 123, "remaining": 377, "state": "normal"}
    assert breadcrumb == [
        {"id": "id:folder-1", "name": "Library"},
        {"id": "id:file-1", "name": "Comic.cbz"},
    ]
    assert recent.items[0].id == "new"
    assert shared.folder_path == "/shared-with-me"
    assert client._request_rpc.await_args_list[0].kwargs["payload"]["limit"] == 200
    assert client._request_rpc.await_args_list[2].kwargs["payload"]["limit"] == 1


@pytest.mark.asyncio
async def test_download_helpers_cover_folder_error_and_write_to_path(tmp_path):
    client = DropboxDriveClient(SimpleNamespace())
    account = _account()
    client._request_content_download = AsyncMock(side_effect=[
        ({".tag": "folder", "name": "Folder"}, b""),
        ({".tag": "file", "name": "Comic.cbz"}, b"payload"),
        ({".tag": "file", "name": "Comic.cbz"}, b"payload"),
    ])

    with pytest.raises(DriveOrganizerError, match="Cannot download a folder"):
        await client.download_file_bytes(account, "id:folder-1")

    filename, content = await client.download_file_bytes(account, "id:file-1")
    target_path = tmp_path / "nested" / "comic.cbz"
    written_filename = await client.download_file_to_path(account, "id:file-1", str(target_path))

    assert filename == "Comic.cbz"
    assert content == b"payload"
    assert written_filename == "Comic.cbz"
    assert target_path.read_bytes() == b"payload"


@pytest.mark.asyncio
async def test_upload_session_chunk_and_mutation_helpers(monkeypatch):
    _DROPBOX_UPLOAD_SESSIONS.clear()
    token_manager = SimpleNamespace(get_valid_access_token=AsyncMock(return_value="token-1"))
    client = DropboxDriveClient(token_manager)
    account = _account()
    http_client = _FakeHttpClient(
        responses=[
            _response(200, text=""),
            _response(200, json_body={"id": "uploaded-1", "name": "Comic.cbz", ".tag": "file"}),
        ]
    )
    monkeypatch.setattr(DropboxDriveClient, "_get_http_client", AsyncMock(return_value=http_client))
    monkeypatch.setattr(
        dropbox_module.provider_request_usage_tracker,
        "record_response",
        AsyncMock(),
    )
    monkeypatch.setattr(
        dropbox_module.provider_request_usage_tracker,
        "record_transport_error",
        AsyncMock(),
    )
    client._request_content_upload = AsyncMock(return_value={"id": "up-1", "name": "Comic.cbz", ".tag": "file"})

    client._request_rpc = AsyncMock(side_effect=[
        {"path_display": "/Library", ".tag": "folder"},
        {"path_display": "/Library", ".tag": "folder"},
        {"session_id": "session-1"},
        {"path_display": "/Library", ".tag": "folder"},
        {"metadata": {"id": "folder-1", "name": "Folder", ".tag": "folder"}},
        {"path_display": "/Library/Old.cbz", "name": "Old.cbz", ".tag": "file", "id": "id:old"},
        {"path_display": "/Archive", ".tag": "folder"},
        {"metadata": {"id": "id:new", "name": "Renamed.cbz", ".tag": "file"}},
        {},
        {".tag": "async_job_id", "async_job_id": "job-1"},
        {".tag": "in_progress"},
        {".tag": "complete"},
        {"path_display": "/Library/Source.cbz", "name": "Source.cbz", ".tag": "file"},
        {"path_display": "/Copies", ".tag": "folder"},
        {},
    ])

    uploaded = await client.upload_small_file(account, "Comic.cbz", BytesIO(b"123"), folder_id="/Library")
    session = await client.create_upload_session(account, "Big.cbz", folder_id="/Library")
    partial = await client.upload_chunk(session["upload_url"], b"chunk", 0, 9, 20, account=account)
    complete = await client.upload_chunk(session["upload_url"], b"chunk", 10, 19, 20, account=account)
    folder = await client.create_folder(account, "Folder", parent_id="/Library")
    updated = await client.update_item(account, "id:old", name="Renamed.cbz", parent_id="/Archive")
    await client.delete_item(account, "id:trash")
    await client.batch_delete_items(account, ["id:one", "id:two"])
    copy_url = await client.copy_item(account, "id:source", name="Copy.cbz", parent_id="/Copies")

    assert uploaded.id == "up-1"
    assert session["upload_url"].startswith("dropbox-session://")
    assert partial == {"next_expected_ranges": ["10-"]}
    assert complete["id"] == "uploaded-1"
    assert folder.item_type == "folder"
    assert updated.name == "Renamed.cbz"
    assert copy_url == "dropbox://copy-complete//Copies/Copy.cbz"
    assert http_client.calls[0][0][0] == f"{DROPBOX_CONTENT_BASE_URL}/files/upload_session/append_v2"
    assert http_client.calls[1][0][0] == f"{DROPBOX_CONTENT_BASE_URL}/files/upload_session/finish"


@pytest.mark.asyncio
async def test_upload_chunk_validates_session_and_transport_errors(monkeypatch):
    _DROPBOX_UPLOAD_SESSIONS.clear()
    upload_url, _expires_at = _session_payload_to_url(
        {
            "provider": "dropbox",
            "session_id": "session-1",
            "commit_path": "/Library/Comic.cbz",
            "account_id": "acc-1",
        }
    )
    token_manager = SimpleNamespace(get_valid_access_token=AsyncMock(return_value="token-1"))
    client = DropboxDriveClient(token_manager)
    account = _account()
    http_client = _FakeHttpClient(error=httpx.ReadTimeout("boom"))
    monkeypatch.setattr(DropboxDriveClient, "_get_http_client", AsyncMock(return_value=http_client))
    monkeypatch.setattr(
        dropbox_module.provider_request_usage_tracker,
        "record_response",
        AsyncMock(),
    )
    transport_error_mock = AsyncMock()
    monkeypatch.setattr(
        dropbox_module.provider_request_usage_tracker,
        "record_transport_error",
        transport_error_mock,
    )

    with pytest.raises(DriveOrganizerError, match="does not match account"):
        await client.upload_chunk(upload_url, b"chunk", 0, 9, 20, account=SimpleNamespace(id="acc-2"))
    with pytest.raises(DriveOrganizerError, match="timed out"):
        await client.upload_chunk(upload_url, b"chunk", 0, 9, 20, account=account)

    transport_error_mock.assert_awaited_once_with(provider="dropbox", kind="timeout")
