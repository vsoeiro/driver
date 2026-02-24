"""Dropbox OAuth2 authentication service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from backend.core.config import get_settings
from backend.security.oauth_types import TokenResult
from backend.services.oauth_http import post_form_with_retry

logger = logging.getLogger(__name__)

DROPBOX_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class DropboxAuthService:
    """Service for Dropbox OAuth2 authorization code flow."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        if not self._settings.dropbox_client_id:
            raise ValueError("DROPBOX_CLIENT_ID is not configured")

        params = {
            "client_id": self._settings.dropbox_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "token_access_type": "offline",
        }
        return f"{DROPBOX_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: str
    ) -> TokenResult | None:
        payload = {
            "code": code,
            "client_id": self._settings.dropbox_client_id,
            "client_secret": self._settings.dropbox_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        return await self._token_request(payload)

    async def refresh_access_token(self, refresh_token: str) -> TokenResult | None:
        payload = {
            "client_id": self._settings.dropbox_client_id,
            "client_secret": self._settings.dropbox_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        result = await self._token_request(payload)
        if result and not result.refresh_token:
            result.refresh_token = refresh_token
        return result

    async def _token_request(self, payload: dict) -> TokenResult | None:
        response = await post_form_with_retry(
            url=DROPBOX_TOKEN_URL,
            payload=payload,
            timeout=DROPBOX_TIMEOUT,
            provider="Dropbox",
        )
        if response is None:
            return None

        data = response.json()
        access_token = data.get("access_token")
        if not access_token:
            logger.error("Dropbox token request did not return access_token: %s", data)
            return None

        expires_in = int(data.get("expires_in", 3600))
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        claims = {}
        if data.get("account_id"):
            claims["account_id"] = data["account_id"]

        return TokenResult(
            access_token=access_token,
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            id_token_claims=claims,
        )


_auth_service: DropboxAuthService | None = None


def get_dropbox_auth_service() -> DropboxAuthService:
    """Get Dropbox OAuth service singleton."""
    global _auth_service
    if _auth_service is None:
        _auth_service = DropboxAuthService()
    return _auth_service
