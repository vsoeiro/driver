from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.core.exceptions import DriveOrganizerError
from backend.services.google.drive.client import (
    FILE_FIELDS,
    GOOGLE_DRIVE_BASE_URL,
    GOOGLE_FOLDER_MIME,
    GoogleDriveClient,
)


def _account():
    return SimpleNamespace(id="acc-1", provider="google")


def _response(status_code: int, *, json_body=None, text: str = "", headers=None):
    request = httpx.Request("GET", "https://google.test")
    kwargs = {"headers": headers or {}}
    if json_body is not None:
        kwargs["json"] = json_body
    else:
        kwargs["content"] = text.encode()
    return httpx.Response(status_code, request=request, **kwargs)


class _FakeHttpClient:
    def __init__(self, *, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def put(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_request_builds_urls_and_maps_http_errors():
    client = GoogleDriveClient(SimpleNamespace())
    account = _account()
    client._perform_oauth_request = AsyncMock(return_value=_response(404, text="missing"))

    with pytest.raises(DriveOrganizerError, match="Google Drive API error"):
        await client._request("GET", "/files", account)

    client._perform_oauth_request = AsyncMock(return_value=_response(308, headers={"Range": "bytes=0-9"}))
    response = await client._request("PUT", "/files", account, use_upload_api=True)

    assert response.status_code == 308
    assert client._perform_oauth_request.await_args.kwargs["url"].startswith("https://www.googleapis.com/upload/drive/v3")


def test_parse_single_item_and_parse_list_cover_files_and_folders():
    client = GoogleDriveClient(SimpleNamespace())

    folder = client._parse_single_item({
        "id": "folder-1",
        "name": "Folder",
        "mimeType": GOOGLE_FOLDER_MIME,
        "quotaBytesUsed": "12",
        "size": "999",
    })
    file_item = client._parse_single_item({
        "id": "file-1",
        "name": "Comic.cbz",
        "mimeType": "application/cbz",
        "size": "2048",
        "createdTime": "2026-03-11T12:00:00Z",
        "modifiedTime": "2026-03-11T12:10:00Z",
        "webViewLink": "https://view",
        "webContentLink": "https://download",
    })
    listing = client._parse_list(
        {"files": [{"id": "file-1", "name": "Comic.cbz", "mimeType": "application/cbz"}], "nextPageToken": "next-1"},
        "/",
        {"q": "trashed=false", "pageSize": 50},
    )

    assert folder.item_type == "folder"
    assert folder.size == 12
    assert file_item.item_type == "file"
    assert file_item.download_url == "https://download"
    assert listing.next_link == f"{GOOGLE_DRIVE_BASE_URL}/files?q=trashed%3Dfalse&pageSize=50&pageToken=next-1"


@pytest.mark.asyncio
async def test_listing_metadata_search_quota_recent_and_shared_helpers():
    client = GoogleDriveClient(SimpleNamespace())
    account = _account()
    client._request = AsyncMock(side_effect=[
        _response(200, json_body={"files": [{"id": "root-file", "name": "Root.cbz", "mimeType": "application/cbz"}]}),
        _response(200, json_body={"files": [{"id": "child-file", "name": "Child.cbz", "mimeType": "application/cbz"}]}),
        _response(200, json_body={"files": [{"id": "paged-file", "name": "Paged.cbz", "mimeType": "application/cbz"}]}),
        _response(200, json_body={"id": "meta-1", "name": "Meta.cbz", "mimeType": "application/cbz"}),
        _response(200, json_body={"files": [{"id": "search-1", "name": "Query.cbz", "mimeType": "application/cbz"}]}),
        _response(200, json_body={"storageQuota": {"limit": "500", "usage": "123"}}),
        _response(200, json_body={"files": [{"id": "recent-1", "name": "Recent.cbz", "mimeType": "application/cbz"}]}),
        _response(200, json_body={"files": [{"id": "shared-1", "name": "Shared.cbz", "mimeType": "application/cbz"}]}),
    ])

    root = await client.list_root_items(account, page_size=500)
    folder = await client.list_folder_items(account, "folder-1", page_size=0)
    paged = await client.list_items_by_next_link(account, "https://www.googleapis.com/drive/v3/files?pageToken=abc&q=test")
    metadata = await client.get_item_metadata(account, "meta-1")
    search = await client.search_items(account, "Dylan Dog")
    quota = await client.get_quota(account)
    recent = await client.get_recent_items(account)
    shared = await client.get_shared_with_me(account)

    assert root.items[0].id == "root-file"
    assert folder.folder_path == "folder-1"
    assert paged.items[0].id == "paged-file"
    assert metadata.id == "meta-1"
    assert search.folder_path == "search:Dylan Dog"
    assert quota == {"total": 500, "used": 123, "remaining": 377, "state": "normal"}
    assert recent.folder_path == "recent"
    assert shared.folder_path == "shared"

    first_params = client._request.await_args_list[0].kwargs["params"]
    second_params = client._request.await_args_list[1].kwargs["params"]
    assert first_params["pageSize"] == 200
    assert second_params["pageSize"] == 1


@pytest.mark.asyncio
async def test_download_helpers_and_item_path_handle_edge_cases():
    client = GoogleDriveClient(SimpleNamespace())
    account = _account()

    client._request = AsyncMock(side_effect=[
        _response(200, json_body={"id": "download-1", "mimeType": "application/cbz", "webContentLink": "https://download"}),
        _response(200, json_body={"id": "doc-1", "mimeType": "application/vnd.google-apps.document"}),
        _response(200, json_body={"id": "no-link", "mimeType": "application/cbz"}),
        _response(200, json_body={"id": "file-1", "name": "Comic.cbz", "mimeType": "application/cbz"}),
        _response(200, json_body={"name": "Comic.cbz"}, text="", headers={}),
        _response(200, json_body={"id": "leaf", "name": "Leaf", "parents": ["parent"]}),
        _response(200, json_body={"id": "parent", "name": "Parent", "parents": ["root"]}),
    ])

    assert await client.get_download_url(account, "download-1") == "https://download"
    with pytest.raises(DriveOrganizerError, match="Google Docs native files"):
        await client.get_download_url(account, "doc-1")
    with pytest.raises(DriveOrganizerError, match="Download URL not available"):
        await client.get_download_url(account, "no-link")

    filename, _content = await client.download_file_bytes(account, "file-1")
    breadcrumb = await client.get_item_path(account, "leaf")

    assert filename == "Comic.cbz"
    assert breadcrumb == [
        {"id": "root", "name": "Root"},
        {"id": "parent", "name": "Parent"},
        {"id": "leaf", "name": "Leaf"},
    ]


@pytest.mark.asyncio
async def test_upload_mutation_delete_and_copy_helpers():
    client = GoogleDriveClient(SimpleNamespace())
    account = _account()

    with pytest.raises(DriveOrganizerError, match="Invalid upload content"):
        await client.upload_small_file(account, "Comic.cbz", "not-bytes")

    client._request = AsyncMock(side_effect=[
        _response(200, json_body={"id": "up-1", "name": "Comic.cbz", "mimeType": "application/cbz"}),
        _response(200, headers={"Location": "https://upload.example/session"}, json_body={}),
        _response(200, json_body={"id": "folder-1", "name": "Folder", "mimeType": GOOGLE_FOLDER_MIME}),
        _response(200, json_body={"parents": ["old-parent"]}),
        _response(200, json_body={"id": "item-1", "name": "Renamed.cbz", "mimeType": "application/cbz"}),
        _response(204, text=""),
        _response(200, json_body={"id": "copy-1", "webViewLink": "https://drive.google.com/file/copy-1"}),
    ])

    uploaded = await client.upload_small_file(account, "Comic.cbz", b"123", folder_id="root")
    session = await client.create_upload_session(account, "Comic.cbz")
    folder = await client.create_folder(account, "Folder")
    updated = await client.update_item(account, "item-1", name="Renamed.cbz", parent_id="new-parent")
    await client.delete_item(account, "item-1")
    copied = await client.copy_item(account, "copy-source", name="Copy.cbz")

    assert uploaded.id == "up-1"
    assert session["upload_url"] == "https://upload.example/session"
    assert folder.item_type == "folder"
    assert updated.name == "Renamed.cbz"
    assert copied == "https://drive.google.com/file/copy-1"
    patch_params = client._request.await_args_list[4].kwargs["params"]
    assert patch_params["addParents"] == "new-parent"
    assert patch_params["removeParents"] == "old-parent"


@pytest.mark.asyncio
async def test_upload_chunk_reports_progress_and_errors(monkeypatch):
    client = GoogleDriveClient(SimpleNamespace())
    http_client = _FakeHttpClient(response=_response(308, headers={"Range": "bytes=0-9"}))
    monkeypatch.setattr(GoogleDriveClient, "_get_http_client", AsyncMock(return_value=http_client))
    monkeypatch.setattr("backend.services.google.drive.client.provider_request_usage_tracker.record_response", AsyncMock())
    monkeypatch.setattr("backend.services.google.drive.client.provider_request_usage_tracker.record_transport_error", AsyncMock())

    partial = await client.upload_chunk("https://upload.example/session", b"chunk", 0, 9, 100)
    assert partial == {"next_expected_ranges": ["10-"]}

    http_client.response = _response(200, json_body={"id": "uploaded-1"})
    complete = await client.upload_chunk("https://upload.example/session", b"chunk", 10, 19, 100)
    assert complete == {"id": "uploaded-1"}

    http_client.error = httpx.ReadTimeout("boom")
    with pytest.raises(DriveOrganizerError, match="timed out"):
        await client.upload_chunk("https://upload.example/session", b"chunk", 20, 29, 100)
