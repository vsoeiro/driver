from unittest.mock import AsyncMock

import httpx
import pytest

from backend.services import oauth_http


class _AsyncClientContext:
    def __init__(self, client):
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_post_form_with_retry_retries_retryable_status_codes(monkeypatch):
    request = httpx.Request("POST", "https://example.test/token")
    fake_client = type(
        "FakeClient",
        (),
        {
            "post": AsyncMock(
                side_effect=[
                    httpx.Response(503, request=request, text="unavailable"),
                    httpx.Response(200, request=request, text="ok"),
                ]
            )
        },
    )()
    sleep_mock = AsyncMock()

    monkeypatch.setattr(oauth_http.httpx, "AsyncClient", lambda timeout: _AsyncClientContext(fake_client))
    monkeypatch.setattr(oauth_http.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(oauth_http.random, "uniform", lambda _start, _end: 0.0)

    response = await oauth_http.post_form_with_retry(
        url="https://example.test/token",
        payload={"code": "abc"},
        timeout=httpx.Timeout(5.0),
        provider="google",
    )

    assert response is not None
    assert response.status_code == 200
    assert fake_client.post.await_count == 2
    sleep_mock.assert_awaited_once_with(0.35)


@pytest.mark.asyncio
async def test_post_form_with_retry_returns_none_for_transport_and_client_errors(monkeypatch):
    request = httpx.Request("POST", "https://example.test/token")

    timeout_client = type(
        "TimeoutClient",
        (),
        {"post": AsyncMock(side_effect=httpx.ConnectError("boom"))},
    )()
    sleep_mock = AsyncMock()

    monkeypatch.setattr(oauth_http.httpx, "AsyncClient", lambda timeout: _AsyncClientContext(timeout_client))
    monkeypatch.setattr(oauth_http.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(oauth_http.random, "uniform", lambda _start, _end: 0.0)

    timeout_result = await oauth_http.post_form_with_retry(
        url="https://example.test/token",
        payload={"code": "abc"},
        timeout=httpx.Timeout(5.0),
        provider="google",
        max_attempts=2,
    )

    assert timeout_result is None
    assert sleep_mock.await_count == 1

    error_client = type(
        "ErrorClient",
        (),
        {"post": AsyncMock(return_value=httpx.Response(400, request=request, text="bad request"))},
    )()
    monkeypatch.setattr(oauth_http.httpx, "AsyncClient", lambda timeout: _AsyncClientContext(error_client))
    sleep_mock.reset_mock()

    error_result = await oauth_http.post_form_with_retry(
        url="https://example.test/token",
        payload={"code": "abc"},
        timeout=httpx.Timeout(5.0),
        provider="google",
    )

    assert error_result is None
    sleep_mock.assert_not_awaited()
