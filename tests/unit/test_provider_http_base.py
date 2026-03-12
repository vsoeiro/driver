from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from backend.services.providers import http_base
from backend.services.providers.http_base import OAuthHTTPClientBase


class _FakeAsyncClient:
    def __init__(self):
        self.aclose = AsyncMock()


@pytest.mark.asyncio
async def test_shared_http_client_is_reused_and_closed(monkeypatch):
    created_clients = []

    def _factory(*, timeout):
        client = _FakeAsyncClient()
        created_clients.append((timeout, client))
        return client

    monkeypatch.setattr(http_base.httpx, "AsyncClient", _factory)
    OAuthHTTPClientBase._shared_client = None
    OAuthHTTPClientBase._shared_client_lock = None

    timeout = httpx.Timeout(5.0)
    client_one = await OAuthHTTPClientBase._get_http_client(timeout=timeout)
    client_two = await OAuthHTTPClientBase._get_http_client(timeout=timeout)

    assert client_one is client_two
    assert len(created_clients) == 1

    await OAuthHTTPClientBase.close_http_client()

    created_clients[0][1].aclose.assert_awaited_once()
    assert OAuthHTTPClientBase._shared_client is None


@pytest.mark.asyncio
async def test_perform_oauth_request_retries_after_unauthorized(monkeypatch):
    request = httpx.Request("GET", "https://example.test/items")
    fake_http_client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                httpx.Response(401, request=request, text="expired"),
                httpx.Response(200, request=request, json={"ok": True}),
            ]
        )
    )
    token_manager = SimpleNamespace(
        get_valid_access_token=AsyncMock(return_value="token-1"),
        force_refresh_access_token=AsyncMock(return_value="token-2"),
    )
    record_response_mock = AsyncMock()
    record_transport_error_mock = AsyncMock()
    retry_log = Mock()

    monkeypatch.setattr(OAuthHTTPClientBase, "_get_http_client", AsyncMock(return_value=fake_http_client))
    monkeypatch.setattr(http_base.provider_request_usage_tracker, "record_response", record_response_mock)
    monkeypatch.setattr(http_base.provider_request_usage_tracker, "record_transport_error", record_transport_error_mock)

    client = OAuthHTTPClientBase(token_manager)
    account = SimpleNamespace(provider="google")
    response = await client._perform_oauth_request(
        method="GET",
        url="https://example.test/items",
        account=account,
        timeout=httpx.Timeout(5.0),
        timeout_error_factory=lambda exc: RuntimeError(f"timeout: {exc}"),
        connection_error_factory=lambda exc: RuntimeError(f"connection: {exc}"),
        request_headers={"X-Test": "1"},
        unauthorized_retry_log=retry_log,
    )

    assert response.status_code == 200
    assert fake_http_client.request.await_args_list[0].kwargs["headers"]["Authorization"] == "Bearer token-1"
    assert fake_http_client.request.await_args_list[1].kwargs["headers"]["Authorization"] == "Bearer token-2"
    retry_log.assert_called_once_with(account)
    token_manager.force_refresh_access_token.assert_awaited_once_with(account)
    assert record_response_mock.await_count == 2
    record_transport_error_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_perform_oauth_request_converts_transport_errors_and_parses_messages(monkeypatch):
    fake_http_client = SimpleNamespace(
        request=AsyncMock(side_effect=httpx.ReadTimeout("boom"))
    )
    token_manager = SimpleNamespace(
        get_valid_access_token=AsyncMock(return_value="token-1"),
        force_refresh_access_token=AsyncMock(),
    )
    record_response_mock = AsyncMock()
    record_transport_error_mock = AsyncMock()

    monkeypatch.setattr(OAuthHTTPClientBase, "_get_http_client", AsyncMock(return_value=fake_http_client))
    monkeypatch.setattr(http_base.provider_request_usage_tracker, "record_response", record_response_mock)
    monkeypatch.setattr(http_base.provider_request_usage_tracker, "record_transport_error", record_transport_error_mock)

    client = OAuthHTTPClientBase(token_manager)
    account = SimpleNamespace(provider="google")

    with pytest.raises(ValueError, match="timeout"):
        await client._perform_oauth_request(
            method="GET",
            url="https://example.test/items",
            account=account,
            timeout=httpx.Timeout(5.0),
            timeout_error_factory=lambda exc: ValueError("timeout"),
            connection_error_factory=lambda exc: RuntimeError("connection"),
        )

    record_response_mock.assert_not_awaited()
    record_transport_error_mock.assert_awaited_once_with(provider="google", kind="timeout")

    nested_error = httpx.Response(
        400,
        request=httpx.Request("GET", "https://example.test/items"),
        json={"error": {"message": "No access"}},
    )
    message_error = httpx.Response(
        400,
        request=httpx.Request("GET", "https://example.test/items"),
        json={"message": "Fallback"},
    )
    text_error = httpx.Response(
        500,
        request=httpx.Request("GET", "https://example.test/items"),
        text="raw error",
    )

    assert OAuthHTTPClientBase.parse_error_message(nested_error) == "No access"
    assert OAuthHTTPClientBase.parse_error_message(message_error) == "Fallback"
    assert OAuthHTTPClientBase.parse_error_message(text_error, default="Request failed") == "raw error"
