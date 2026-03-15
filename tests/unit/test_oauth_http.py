from unittest.mock import AsyncMock

import httpx
import pytest

from backend.services import oauth_http
from backend.services.oauth_http import OAuthTokenRequestError


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
async def test_post_form_with_retry_raises_transient_error_after_transport_retries(monkeypatch):
    timeout_client = type(
        "TimeoutClient",
        (),
        {"post": AsyncMock(side_effect=httpx.ConnectError("boom"))},
    )()
    sleep_mock = AsyncMock()

    monkeypatch.setattr(oauth_http.httpx, "AsyncClient", lambda timeout: _AsyncClientContext(timeout_client))
    monkeypatch.setattr(oauth_http.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(oauth_http.random, "uniform", lambda _start, _end: 0.0)

    with pytest.raises(OAuthTokenRequestError) as exc_info:
        await oauth_http.post_form_with_retry(
            url="https://example.test/token",
            payload={"code": "abc"},
            timeout=httpx.Timeout(5.0),
            provider="google",
            max_attempts=2,
        )

    assert exc_info.value.transient is True
    assert "boom" in (exc_info.value.details or "")
    assert sleep_mock.await_count == 1


@pytest.mark.asyncio
async def test_post_form_with_retry_raises_provider_error_details_for_client_errors(monkeypatch):
    request = httpx.Request("POST", "https://example.test/token")

    error_client = type(
        "ErrorClient",
        (),
        {
            "post": AsyncMock(
                return_value=httpx.Response(
                    400,
                    request=request,
                    json={
                        "error": "invalid_grant",
                        "error_description": "Token has been expired or revoked.",
                    },
                )
            )
        },
    )()
    monkeypatch.setattr(oauth_http.httpx, "AsyncClient", lambda timeout: _AsyncClientContext(error_client))
    sleep_mock = AsyncMock()
    monkeypatch.setattr(oauth_http.asyncio, "sleep", sleep_mock)

    with pytest.raises(OAuthTokenRequestError) as exc_info:
        await oauth_http.post_form_with_retry(
            url="https://example.test/token",
            payload={"code": "abc"},
            timeout=httpx.Timeout(5.0),
            provider="google",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "invalid_grant"
    assert exc_info.value.transient is False
    assert exc_info.value.details == "Token has been expired or revoked."
    sleep_mock.assert_not_awaited()
