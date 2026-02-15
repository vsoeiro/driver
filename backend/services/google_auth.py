"""Google OAuth2 authentication service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt

from backend.core.config import get_settings
from backend.services.oauth_types import TokenResult

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class GoogleAuthService:
    """Service for Google OAuth2 authorization code flow."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        """Build Google authorization URL."""
        if not self._settings.google_client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured")

        params = {
            "client_id": self._settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self._settings.google_scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> TokenResult | None:
        """Exchange authorization code for access/refresh tokens."""
        payload = {
            "code": code,
            "client_id": self._settings.google_client_id,
            "client_secret": self._settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        return self._token_request(payload)

    def refresh_access_token(self, refresh_token: str) -> TokenResult | None:
        """Refresh an expired Google access token."""
        payload = {
            "client_id": self._settings.google_client_id,
            "client_secret": self._settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        result = self._token_request(payload)
        if result and not result.refresh_token:
            result.refresh_token = refresh_token
        return result

    def _token_request(self, payload: dict) -> TokenResult | None:
        try:
            response = httpx.post(
                GOOGLE_TOKEN_URL,
                data=payload,
                timeout=GOOGLE_TIMEOUT,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            details = ""
            if getattr(exc, "response", None) is not None and exc.response is not None:
                details = exc.response.text
            logger.error("Google token request failed: %s %s", exc, details)
            return None

        data = response.json()
        access_token = data.get("access_token")
        if not access_token:
            logger.error("Google token request did not return access_token: %s", data)
            return None

        expires_in = int(data.get("expires_in", 3600))
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        id_token_claims: dict = {}
        id_token = data.get("id_token")
        if id_token:
            try:
                id_token_claims = jwt.decode(
                    id_token,
                    options={"verify_signature": False, "verify_aud": False},
                    algorithms=["RS256", "HS256", "ES256"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not decode Google id_token claims: %s", exc)

        return TokenResult(
            access_token=access_token,
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            id_token_claims=id_token_claims,
        )


_auth_service: GoogleAuthService | None = None


def get_google_auth_service() -> GoogleAuthService:
    """Get Google OAuth service singleton."""
    global _auth_service
    if _auth_service is None:
        _auth_service = GoogleAuthService()
    return _auth_service
