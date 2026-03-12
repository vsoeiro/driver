from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.core.exceptions import GraphAPIError
from backend.services.microsoft.onedrive import client as graph_module
from backend.services.microsoft.onedrive.client import (
    GRAPH_BASE_URL,
    GRAPH_THROTTLE_MAX_DELAY_SECONDS,
    GraphClient,
    _encode_drive_path_component,
)


def _account():
    return SimpleNamespace(id="acc-1", provider="microsoft")


def _response(status_code: int, *, json_body=None, text: str = "", headers=None):
    request = httpx.Request("GET", "https://graph.test")
    kwargs = {"headers": headers or {}}
    if json_body is not None:
        kwargs["json"] = json_body
    else:
        kwargs["content"] = text.encode()
    return httpx.Response(status_code, request=request, **kwargs)


class _FakeHttpClient:
    def __init__(self, *, get_responses=None, put_responses=None, error=None):
        self._get_responses = list(get_responses or [])
        self._put_responses = list(put_responses or [])
        self.error = error
        self.get_calls = []
        self.put_calls = []

    async def get(self, *args, **kwargs):
        self.get_calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self._get_responses.pop(0)

    async def put(self, *args, **kwargs):
        self.put_calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self._put_responses.pop(0)


class _FakeStreamResponse:
    def __init__(self, status_code: int, *, chunks=None, text: str = "", headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = list(chunks or [])
        self._content = text.encode()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    async def aread(self):
        return self._content


class _FakeStreamClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def stream(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._responses.pop(0)


def test_graph_helpers_parse_retry_delay_and_items(monkeypatch):
    retry_after = _response(429, headers={"Retry-After": "42"})
    no_retry_after = _response(429, headers={"Retry-After": "abc"})
    negative_retry_after = _response(429, headers={"Retry-After": "-1"})
    monkeypatch.setattr(graph_module.random, "uniform", lambda _start, _end: 0.25)

    client = GraphClient(SimpleNamespace())
    folder = client._parse_single_item({
        "id": "folder-1",
        "name": "Folder",
        "folder": {"childCount": 4},
        "size": 99,
    })
    file_item = client._parse_single_item({
        "id": "file-1",
        "name": "Comic.cbz",
        "size": 2048,
        "file": {"mimeType": "application/cbz"},
        "@microsoft.graph.downloadUrl": "https://download",
        "webUrl": "https://view",
    })
    listing = client._parse_drive_items(
        {
            "value": [{"id": "file-1", "name": "Comic.cbz", "file": {"mimeType": "application/cbz"}}],
            "@odata.nextLink": "https://graph.test/next",
        },
        "/",
    )

    assert GraphClient._parse_retry_after_seconds(retry_after) == 42.0
    assert GraphClient._parse_retry_after_seconds(no_retry_after) is None
    assert GraphClient._parse_retry_after_seconds(negative_retry_after) is None
    assert GraphClient._build_throttle_delay_seconds(1, retry_after) == GRAPH_THROTTLE_MAX_DELAY_SECONDS
    assert GraphClient._build_throttle_delay_seconds(3, _response(429)) == 2.25
    assert GraphClient._build_download_retry_delay_seconds(2) == 1.25
    assert _encode_drive_path_component("Folder Name/Comic.cbz") == "Folder%20Name%2FComic.cbz"
    assert folder.item_type == "folder"
    assert folder.child_count == 4
    assert file_item.item_type == "file"
    assert file_item.download_url == "https://download"
    assert listing.next_link == "https://graph.test/next"


@pytest.mark.asyncio
async def test_request_retries_throttled_responses_and_maps_errors(monkeypatch):
    client = GraphClient(SimpleNamespace())
    account = _account()
    sleep_mock = AsyncMock()
    monkeypatch.setattr(graph_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(graph_module.random, "uniform", lambda _start, _end: 0.0)

    client._perform_oauth_request = AsyncMock(side_effect=[
        _response(429, text="busy"),
        _response(200, json_body={"ok": True}),
        _response(204, text=""),
        _response(400, json_body={"error": {"message": "denied"}}),
    ])

    result = await client._request("GET", "/me", account)
    empty = await client._request("DELETE", "https://graph.test/items/1", account)

    with pytest.raises(GraphAPIError, match="denied"):
        await client._request("GET", "/fail", account)

    assert result == {"ok": True}
    assert empty == {}
    assert client._perform_oauth_request.await_args_list[0].kwargs["url"] == f"{GRAPH_BASE_URL}/me"
    assert client._perform_oauth_request.await_args_list[2].kwargs["url"] == "https://graph.test/items/1"
    sleep_mock.assert_awaited_once_with(0.5)


@pytest.mark.asyncio
async def test_listing_search_quota_recent_shared_and_metadata_helpers():
    client = GraphClient(SimpleNamespace())
    account = _account()
    client._request = AsyncMock(side_effect=[
        {"value": [{"id": "root-file", "name": "Root.cbz", "file": {"mimeType": "application/cbz"}}]},
        {"value": [{"id": "child-file", "name": "Child.cbz", "file": {"mimeType": "application/cbz"}}]},
        {"value": [{"id": "paged-file", "name": "Paged.cbz", "file": {"mimeType": "application/cbz"}}]},
        {"id": "meta-1", "name": "Meta.cbz", "file": {"mimeType": "application/cbz"}},
        {"value": [{"id": "search-1", "name": "Query.cbz", "file": {"mimeType": "application/cbz"}}]},
        {"quota": {"total": 500, "used": 123, "remaining": 377, "state": "normal"}},
        {"value": [{"id": "recent-1", "name": "Recent.cbz", "file": {"mimeType": "application/cbz"}}]},
        {"value": [{"id": "shared-1", "name": "Shared.cbz", "file": {"mimeType": "application/cbz"}}]},
    ])

    root = await client.list_root_items(account, page_size=500)
    folder = await client.list_folder_items(account, "folder-1", page_size=0)
    paged = await client.list_items_by_next_link(account, "https://graph.test/next")
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
    assert client._request.await_args_list[0].kwargs["params"]["$top"] == 200
    assert client._request.await_args_list[1].kwargs["params"]["$top"] == 1
    assert "Dylan%20Dog" in client._request.await_args_list[4].args[1]


@pytest.mark.asyncio
async def test_download_helpers_cover_errors_retries_and_breadcrumb(monkeypatch):
    client = GraphClient(SimpleNamespace())
    account = _account()
    sleep_mock = AsyncMock()
    http_client = _FakeHttpClient(
        get_responses=[
            _response(429, text="busy"),
            _response(200, text="payload"),
        ]
    )
    monkeypatch.setattr(GraphClient, "_get_http_client", AsyncMock(return_value=http_client))
    monkeypatch.setattr(graph_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(graph_module.random, "uniform", lambda _start, _end: 0.0)
    monkeypatch.setattr(
        graph_module.provider_request_usage_tracker,
        "record_response",
        AsyncMock(),
    )
    monkeypatch.setattr(
        graph_module.provider_request_usage_tracker,
        "record_transport_error",
        AsyncMock(),
    )

    client._request = AsyncMock(side_effect=[
        {"id": "download-1", "@microsoft.graph.downloadUrl": "https://download"},
        {"id": "no-link"},
        {"id": "folder-1", "folder": {}},
        {"id": "file-1", "name": "Comic.cbz", "@microsoft.graph.downloadUrl": "https://download"},
        {"id": "file-1", "name": "Comic.cbz", "@microsoft.graph.downloadUrl": "https://download"},
        {"id": "leaf", "name": "Leaf", "parentReference": {"id": "parent"}},
        {"id": "parent", "name": "Parent", "parentReference": {"id": "root"}},
        {"id": "root", "name": "Root", "root": {}},
    ])

    assert await client.get_download_url(account, "download-1") == "https://download"
    with pytest.raises(GraphAPIError, match="Download URL not available"):
        await client.get_download_url(account, "no-link")
    with pytest.raises(GraphAPIError, match="Cannot download a folder"):
        await client.download_file_bytes(account, "folder-1")

    filename, content = await client.download_file_bytes(account, "file-1")
    breadcrumb = await client.get_item_path(account, "leaf")

    assert filename == "Comic.cbz"
    assert content == b"payload"
    assert breadcrumb == [
        {"id": "root", "name": "Root"},
        {"id": "parent", "name": "Parent"},
        {"id": "leaf", "name": "Leaf"},
    ]
    sleep_mock.assert_awaited_once_with(0.5)


@pytest.mark.asyncio
async def test_download_file_to_path_streams_with_retry(tmp_path, monkeypatch):
    client = GraphClient(SimpleNamespace())
    account = _account()
    sleep_mock = AsyncMock()
    stream_client = _FakeStreamClient([
        _FakeStreamResponse(503, text="retry"),
        _FakeStreamResponse(200, chunks=[b"ab", b"cd"]),
    ])
    monkeypatch.setattr(GraphClient, "_get_http_client", AsyncMock(return_value=stream_client))
    monkeypatch.setattr(graph_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(graph_module.random, "uniform", lambda _start, _end: 0.0)
    monkeypatch.setattr(
        graph_module.provider_request_usage_tracker,
        "record_response",
        AsyncMock(),
    )
    monkeypatch.setattr(
        graph_module.provider_request_usage_tracker,
        "record_transport_error",
        AsyncMock(),
    )

    client._request = AsyncMock(side_effect=[
        {"id": "file-1", "name": "Comic.cbz", "@microsoft.graph.downloadUrl": "https://download"},
        {"id": "file-1", "name": "Comic.cbz", "@microsoft.graph.downloadUrl": "https://download"},
    ])

    target_path = tmp_path / "downloaded.bin"
    filename = await client.download_file_to_path(account, "file-1", str(target_path))

    assert filename == "Comic.cbz"
    assert target_path.read_bytes() == b"abcd"
    sleep_mock.assert_awaited_once_with(0.5)


@pytest.mark.asyncio
async def test_upload_mutation_delete_batch_and_copy_helpers(monkeypatch):
    client = GraphClient(SimpleNamespace(get_valid_access_token=AsyncMock(return_value="token")))
    account = _account()
    sleep_mock = AsyncMock()
    http_client = _FakeHttpClient(
        put_responses=[
            _response(202, json_body={"nextExpectedRanges": ["10-"]}),
            _response(201, json_body={"id": "uploaded-1"}),
        ]
    )
    monkeypatch.setattr(GraphClient, "_get_http_client", AsyncMock(return_value=http_client))
    monkeypatch.setattr(graph_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(
        graph_module.provider_request_usage_tracker,
        "record_response",
        AsyncMock(),
    )
    monkeypatch.setattr(
        graph_module.provider_request_usage_tracker,
        "record_transport_error",
        AsyncMock(),
    )

    client._perform_oauth_request = AsyncMock(side_effect=[
        _response(200, json_body={"id": "up-1", "name": "Comic.cbz", "file": {"mimeType": "application/cbz"}}),
        _response(202, text="", headers={"Location": "https://graph.test/monitor"}),
        _response(202, text="", headers={}),
        _response(400, json_body={"error": {"message": "copy failed"}}),
    ])
    client._request = AsyncMock(side_effect=[
        {"uploadUrl": "https://graph.test/upload", "expirationDateTime": "2026-03-11T12:00:00Z"},
        {"id": "folder-1", "name": "Folder", "folder": {}},
        {"id": "meta-1", "name": "Current.cbz", "file": {"mimeType": "application/cbz"}},
        {"id": "updated-1", "name": "Renamed.cbz", "file": {"mimeType": "application/cbz"}},
        {},
        {},
        {},
    ])

    uploaded = await client.upload_small_file(account, "Comic.cbz", BytesIO(b"123"), folder_id="root")
    session = await client.create_upload_session(account, "Comic.cbz", folder_id="folder-1")
    partial = await client.upload_chunk("https://graph.test/upload", b"chunk", 0, 9, 20)
    complete = await client.upload_chunk("https://graph.test/upload", b"chunk", 10, 19, 20)
    folder = await client.create_folder(account, "Folder")
    unchanged = await client.update_item(account, "meta-1")
    updated = await client.update_item(account, "updated-1", name="Renamed.cbz", parent_id="root")
    await client.delete_item(account, "deleted-1")
    await client.batch_delete_items(account, ["one", "two"])
    monitor_url = await client.copy_item(account, "copy-1", name="Copy.cbz")

    with pytest.raises(GraphAPIError, match="no monitor URL"):
        await client.copy_item(account, "copy-2")
    with pytest.raises(GraphAPIError, match="copy failed"):
        await client.copy_item(account, "copy-3")

    assert uploaded.id == "up-1"
    assert session["upload_url"] == "https://graph.test/upload"
    assert partial == {"nextExpectedRanges": ["10-"]}
    assert complete == {"id": "uploaded-1"}
    assert folder.item_type == "folder"
    assert unchanged.id == "meta-1"
    assert updated.name == "Renamed.cbz"
    assert monitor_url == "https://graph.test/monitor"
    assert client._request.await_args_list[3].kwargs["json"] == {
        "name": "Renamed.cbz",
        "parentReference": {"id": "root"},
    }
    assert http_client.put_calls[0][1]["headers"]["Content-Range"] == "bytes 0-9/20"
