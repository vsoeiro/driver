from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api.routes import auth as auth_routes


def _make_request(*, scheme="https", path="/auth/callback", cookies=None, headers=None, query_string=""):
    raw_headers = []
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode()))
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), value.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": raw_headers,
        "query_string": query_string.encode(),
        "scheme": scheme,
        "client": ("testclient", 123),
        "server": ("testserver", 443 if scheme == "https" else 80),
    }
    return Request(scope)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_google_login_sets_state_cookie(monkeypatch):
    settings = SimpleNamespace(
        google_client_id="gid",
        google_client_secret="gsecret",
        google_redirect_uri="https://backend.example/google/callback",
    )
    service = SimpleNamespace(get_auth_url=lambda redirect_uri, state: f"https://accounts.example/{redirect_uri}/{state}")
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_routes, "get_google_auth_service", lambda: service)
    monkeypatch.setattr(auth_routes.secrets, "token_urlsafe", lambda _: "state-123")
    monkeypatch.setattr(auth_routes, "encrypt_token", lambda value: f"enc:{value}")

    response = await auth_routes.google_login(_make_request())

    assert response.status_code == 302
    assert response.headers["location"].endswith("/state-123")
    assert "oauth_google_state=enc:state-123" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_google_login_requires_configuration(monkeypatch):
    settings = SimpleNamespace(
        google_client_id="",
        google_client_secret="",
    )
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_routes, "get_google_auth_service", lambda: object())

    with pytest.raises(HTTPException) as exc_info:
        await auth_routes.google_login(_make_request())

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_google_callback_requires_cookie(monkeypatch):
    monkeypatch.setattr(auth_routes, "get_google_auth_service", lambda: object())
    monkeypatch.setattr(auth_routes, "get_settings", lambda: SimpleNamespace(google_redirect_uri="https://backend.example/google/callback"))

    with pytest.raises(HTTPException) as exc_info:
        await auth_routes.google_callback(
            _make_request(cookies={}),
            db=object(),
            code="code-1",
            state="state-1",
        )

    assert exc_info.value.status_code == 400
    assert "Session expired" in exc_info.value.detail


@pytest.mark.asyncio
async def test_google_callback_validates_state(monkeypatch):
    monkeypatch.setattr(auth_routes, "get_google_auth_service", lambda: object())
    monkeypatch.setattr(auth_routes, "get_settings", lambda: SimpleNamespace(google_redirect_uri="https://backend.example/google/callback"))
    monkeypatch.setattr(auth_routes, "decrypt_token", lambda _: "different-state")

    with pytest.raises(HTTPException) as exc_info:
        await auth_routes.google_callback(
            _make_request(cookies={"oauth_google_state": "enc-state"}),
            db=object(),
            code="code-1",
            state="state-1",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid session state."


@pytest.mark.asyncio
async def test_google_callback_persists_account_and_redirects(monkeypatch):
    settings = SimpleNamespace(
        google_redirect_uri="https://backend.example/google/callback",
        frontend_oauth_success_url="https://frontend.example/accounts",
    )
    token_result = SimpleNamespace(
        id_token_claims={"sub": "google-user-1", "email": "reader@example.com", "name": "Reader"},
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at="2026-03-10T12:00:00Z",
    )
    service = SimpleNamespace(exchange_code_for_tokens=AsyncMock(return_value=token_result))
    upsert_mock = AsyncMock()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_routes, "get_google_auth_service", lambda: service)
    monkeypatch.setattr(auth_routes, "decrypt_token", lambda _: "state-1")
    monkeypatch.setattr(auth_routes, "_upsert_linked_account", upsert_mock)

    db = object()
    response = await auth_routes.google_callback(
        _make_request(cookies={"oauth_google_state": "enc-state"}),
        db=db,
        code="code-1",
        state="state-1",
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://frontend.example/accounts"
    upsert_mock.assert_awaited_once_with(
        db=db,
        provider="google",
        provider_account_id="google-user-1",
        email="reader@example.com",
        name="Reader",
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at="2026-03-10T12:00:00Z",
    )


@pytest.mark.asyncio
async def test_microsoft_login_sets_encrypted_flow_cookie(monkeypatch):
    settings = SimpleNamespace(redirect_uri="https://backend.example/microsoft/callback")
    service = SimpleNamespace(get_auth_flow=lambda redirect_uri: {"auth_uri": f"https://login.example/{redirect_uri}", "state": "ms-state"})
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_routes, "get_microsoft_auth_service", lambda: service)
    monkeypatch.setattr(auth_routes, "encrypt_token", lambda value: f"enc:{value}")

    response = await auth_routes.microsoft_login(_make_request())

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://login.example/")
    assert "oauth_flow=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_microsoft_callback_validates_state(monkeypatch):
    settings = SimpleNamespace(frontend_oauth_success_url="https://frontend.example/accounts")
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_routes, "get_microsoft_auth_service", lambda: object())
    monkeypatch.setattr(auth_routes, "decrypt_token", lambda _: '{"state":"expected"}')

    with pytest.raises(HTTPException) as exc_info:
        await auth_routes.microsoft_callback(
            _make_request(cookies={"oauth_flow": "enc-flow"}),
            db=object(),
            code="code-1",
            state="different",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid session state."


@pytest.mark.asyncio
async def test_microsoft_callback_persists_account_and_redirects(monkeypatch):
    settings = SimpleNamespace(frontend_oauth_success_url="https://frontend.example/accounts")
    token_result = SimpleNamespace(
        id_token_claims={"oid": "ms-user-1", "preferred_username": "reader@example.com", "name": "Reader"},
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at="2026-03-10T12:00:00Z",
    )
    service = SimpleNamespace(exchange_code_for_tokens=AsyncMock(return_value=token_result))
    upsert_mock = AsyncMock()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_routes, "get_microsoft_auth_service", lambda: service)
    monkeypatch.setattr(auth_routes, "decrypt_token", lambda _: '{"state":"state-1"}')
    monkeypatch.setattr(auth_routes, "_upsert_linked_account", upsert_mock)

    db = object()
    response = await auth_routes.microsoft_callback(
        _make_request(cookies={"oauth_flow": "enc-flow"}, query_string="code=code-1&state=state-1"),
        db=db,
        code="code-1",
        state="state-1",
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://frontend.example/accounts"
    upsert_mock.assert_awaited_once_with(
        db=db,
        provider="microsoft",
        provider_account_id="ms-user-1",
        email="reader@example.com",
        name="Reader",
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at="2026-03-10T12:00:00Z",
    )


@pytest.mark.asyncio
async def test_upsert_linked_account_updates_existing_record(monkeypatch):
    existing = SimpleNamespace(
        access_token_encrypted="old",
        refresh_token_encrypted="old-refresh",
        token_expires_at=None,
        is_active=False,
        display_name="Old",
        email="old@example.com",
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(existing)),
        add=Mock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(auth_routes, "encrypt_token", lambda value: f"enc:{value}")

    await auth_routes._upsert_linked_account(
        db=db,
        provider="google",
        provider_account_id="google-user-1",
        email="reader@example.com",
        name="Reader",
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at="2026-03-10T12:00:00Z",
    )

    assert existing.access_token_encrypted == "enc:access-1"
    assert existing.refresh_token_encrypted == "enc:refresh-1"
    assert existing.is_active is True
    assert existing.display_name == "Reader"
    db.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_upsert_linked_account_creates_new_record(monkeypatch):
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(None)),
        add=Mock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(auth_routes, "encrypt_token", lambda value: f"enc:{value}")

    await auth_routes._upsert_linked_account(
        db=db,
        provider="dropbox",
        provider_account_id="dropbox-user-1",
        email="reader@example.com",
        name="Reader",
        access_token="access-1",
        refresh_token=None,
        expires_at="2026-03-10T12:00:00Z",
    )

    db.add.assert_called_once()
    created = db.add.call_args.args[0]
    assert created.provider == "dropbox"
    assert created.provider_account_id == "dropbox-user-1"
    assert created.access_token_encrypted == "enc:access-1"
    db.commit.assert_awaited_once_with()


def test_success_redirect_response_falls_back_for_invalid_urls():
    response = auth_routes._success_redirect_response("javascript:alert(1)")

    assert response.headers["location"] == "http://localhost:5173/accounts"


def test_request_is_secure_uses_forwarded_proto_when_present():
    request = _make_request(scheme="http", headers={"x-forwarded-proto": "https"})

    assert auth_routes._request_is_secure(request) is True
