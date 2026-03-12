from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.core.exceptions import TokenRefreshError
from backend.security.token_manager import TokenManager


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


def _account(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "provider": "google",
        "access_token_encrypted": "enc-access",
        "refresh_token_encrypted": "enc-refresh",
        "token_expires_at": now + timedelta(hours=1),
        "is_active": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _manager(*, db=None, microsoft=None, google=None, dropbox=None):
    db = db or AsyncMock()
    with patch("backend.security.token_manager.get_microsoft_auth_service", return_value=microsoft or AsyncMock()), \
        patch("backend.security.token_manager.get_google_auth_service", return_value=google or AsyncMock()), \
        patch("backend.security.token_manager.get_dropbox_auth_service", return_value=dropbox or AsyncMock()):
        return TokenManager(db)


@pytest.mark.asyncio
async def test_get_valid_access_token_returns_cached_token_when_valid():
    account = _account(provider="google")
    manager = _manager()

    with patch("backend.security.token_manager.decrypt_token", return_value="cached-token"):
        token = await manager.get_valid_access_token(account)

    assert token == "cached-token"


@pytest.mark.asyncio
async def test_get_valid_access_token_forces_refresh_when_cached_microsoft_token_is_malformed():
    account = _account(provider="microsoft")
    manager = _manager()
    manager._refresh_token = AsyncMock(return_value="fresh-token")

    with patch("backend.security.token_manager.decrypt_token", return_value="bad token with spaces"):
        token = await manager.get_valid_access_token(account)

    assert token == "fresh-token"
    manager._refresh_token.assert_awaited_once_with(account, force=True)


@pytest.mark.asyncio
async def test_refresh_token_returns_recently_refreshed_locked_token_and_updates_account():
    account = _account(access_token_encrypted="stale")
    locked_account = _account(access_token_encrypted="fresh", refresh_token_encrypted="fresh-refresh")
    db = AsyncMock()
    db.execute.return_value = _ScalarOneResult(locked_account)
    manager = _manager(db=db)

    with patch("backend.security.token_manager.decrypt_token", return_value="already-valid"):
        token = await manager._refresh_token(account, force=False)

    assert token == "already-valid"
    assert account.access_token_encrypted == "fresh"
    assert account.refresh_token_encrypted == "fresh-refresh"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_token_marks_account_inactive_when_refresh_token_is_missing():
    locked_account = _account(refresh_token_encrypted=None)
    db = AsyncMock()
    db.execute.return_value = _ScalarOneResult(locked_account)
    manager = _manager(db=db)
    manager._mark_account_inactive = AsyncMock()

    with pytest.raises(TokenRefreshError, match="No refresh token available"):
        await manager._refresh_token(locked_account)

    manager._mark_account_inactive.assert_awaited_once_with(locked_account)


@pytest.mark.asyncio
async def test_refresh_token_raises_when_refresh_token_cannot_be_decrypted():
    locked_account = _account()
    db = AsyncMock()
    db.execute.return_value = _ScalarOneResult(locked_account)
    manager = _manager(db=db)
    manager._mark_account_inactive = AsyncMock()

    with patch("backend.security.token_manager.decrypt_token", return_value=None):
        with pytest.raises(TokenRefreshError, match="Failed to decrypt refresh token"):
            await manager._refresh_token(locked_account)

    manager._mark_account_inactive.assert_awaited_once_with(locked_account)


@pytest.mark.asyncio
async def test_refresh_token_persists_new_tokens_and_updates_original_account():
    refresh_result = SimpleNamespace(
        access_token="new-access",
        refresh_token="new-refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    auth_service = SimpleNamespace(refresh_access_token=AsyncMock(return_value=refresh_result))
    locked_account = _account(provider="google")
    original_account = _account(provider="google")
    db = AsyncMock()
    db.execute.return_value = _ScalarOneResult(locked_account)
    manager = _manager(db=db, google=auth_service)

    with patch("backend.security.token_manager.decrypt_token", return_value="refresh-token"), \
        patch("backend.security.token_manager.encrypt_token", side_effect=lambda value: f"enc:{value}"):
        token = await manager._refresh_token(original_account, force=True)

    assert token == "new-access"
    assert locked_account.access_token_encrypted == "enc:new-access"
    assert locked_account.refresh_token_encrypted == "enc:new-refresh"
    assert original_account.access_token_encrypted == "enc:new-access"
    db.commit.assert_awaited_once()


def test_auth_service_resolution_and_access_token_shape_checks():
    microsoft_service = AsyncMock()
    google_service = AsyncMock()
    dropbox_service = AsyncMock()
    manager = _manager(microsoft=microsoft_service, google=google_service, dropbox=dropbox_service)

    assert manager._get_auth_service("microsoft") is microsoft_service
    assert manager._get_auth_service("google") is google_service
    assert manager._get_auth_service("dropbox") is dropbox_service
    assert manager._looks_like_valid_access_token("microsoft", "abc" * 10) is True
    assert manager._looks_like_valid_access_token("microsoft", "bad token") is False
    assert manager._looks_like_valid_access_token("google", "opaque-token") is True
    assert manager._looks_like_valid_access_token("google", "") is False

    with pytest.raises(TokenRefreshError, match="Unsupported provider"):
        manager._get_auth_service("box")


@pytest.mark.asyncio
async def test_mark_account_inactive_and_store_tokens_commit_changes():
    db = AsyncMock()
    manager = _manager(db=db)
    account = _account(is_active=True)

    await manager._mark_account_inactive(account)
    assert account.is_active is False

    with patch("backend.security.token_manager.encrypt_token", side_effect=lambda value: f"enc:{value}"):
        await manager.store_tokens(
            account,
            access_token="fresh-access",
            refresh_token="fresh-refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=3),
        )

    assert account.access_token_encrypted == "enc:fresh-access"
    assert account.refresh_token_encrypted == "enc:fresh-refresh"
    assert account.is_active is True
    assert db.commit.await_count == 2
