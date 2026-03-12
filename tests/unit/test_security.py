from __future__ import annotations

import base64
from datetime import timedelta
from unittest.mock import patch

import pytest

from backend.core import security


def _settings(*, secret: str = "super-secret", key: str | None = None):
    encryption_key = key or base64.urlsafe_b64encode(b"1" * 32).decode()
    return type(
        "Settings",
        (),
        {
            "app_secret_key": secret,
            "token_encryption_key": encryption_key,
        },
    )()


@pytest.fixture(autouse=True)
def reset_fernet_cache():
    security._fernet = None
    yield
    security._fernet = None


def test_encrypt_and_decrypt_token_round_trip():
    with patch("backend.core.security.get_settings", return_value=_settings()):
        encrypted = security.encrypt_token("refresh-token")
        decrypted = security.decrypt_token(encrypted)

    assert encrypted != "refresh-token"
    assert decrypted == "refresh-token"


def test_decrypt_token_handles_nested_encryption_and_invalid_values():
    with patch("backend.core.security.get_settings", return_value=_settings()):
        nested = security.encrypt_token(security.encrypt_token("nested-token"))
        assert security.decrypt_token(nested) == "nested-token"
        assert security.decrypt_token("not-a-token") is None
        assert security.decrypt_token("   ") is None


def test_get_fernet_rejects_invalid_key():
    with patch("backend.core.security.get_settings", return_value=_settings(key="invalid")):
        with pytest.raises(ValueError, match="TOKEN_ENCRYPTION_KEY"):
            security._get_fernet()


def test_create_and_decode_jwt_token():
    with patch("backend.core.security.get_settings", return_value=_settings(secret="jwt-secret")):
        token = security.create_jwt_token("user-123")
        payload = security.decode_jwt_token(token)

    assert payload is not None
    assert payload["sub"] == "user-123"


def test_decode_jwt_token_returns_none_for_expired_and_invalid_tokens():
    with patch("backend.core.security.get_settings", return_value=_settings(secret="jwt-secret")):
        expired_token = security.create_jwt_token("user-123", expires_delta=timedelta(seconds=-1))
        assert security.decode_jwt_token(expired_token) is None
        assert security.decode_jwt_token("bad-token") is None
