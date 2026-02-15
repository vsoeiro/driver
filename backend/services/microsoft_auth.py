"""Microsoft OAuth2 authentication service.

This module handles OAuth2 authentication flow with Microsoft Identity Platform
using MSAL (Microsoft Authentication Library).
"""

import logging
from datetime import UTC, datetime, timedelta

import msal

from backend.core.config import get_settings
from backend.services.oauth_types import TokenResult

logger = logging.getLogger(__name__)


class MicrosoftAuthService:
    """Service for Microsoft OAuth2 authentication.

    This service handles the OAuth2 authorization code flow with PKCE
    for securely authenticating users with Microsoft accounts.
    """

    def __init__(self) -> None:
        """Initialize the Microsoft authentication service."""
        self._settings = get_settings()
        self._app = msal.ConfidentialClientApplication(
            client_id=self._settings.microsoft_client_id,
            client_credential=self._settings.microsoft_client_secret,
            authority=self._settings.microsoft_authority,
        )

    def get_auth_flow(self, redirect_uri: str) -> dict:
        """Generate the Microsoft OAuth authorization flow.

        Parameters
        ----------
        redirect_uri : str
            The callback URI after authentication.

        Returns
        -------
        dict
            The authentication flow dictionary containing state and auth URI.
        """
        return self._app.initiate_auth_code_flow(
            scopes=self._settings.microsoft_scopes,
            redirect_uri=redirect_uri,
            prompt="select_account",
        )

    def exchange_code_for_tokens(
        self,
        auth_flow: dict,
        auth_response: dict,
    ) -> TokenResult | None:
        """Exchange authorization code for tokens.

        Parameters
        ----------
        auth_flow : dict
            The original authentication flow dictionary (restored from state).
        auth_response : dict
            The query parameters being returned from the authorization endpoint.

        Returns
        -------
        TokenResult or None
            Token result if successful, None otherwise.
        """
        result = self._app.acquire_token_by_auth_code_flow(
            auth_code_flow=auth_flow,
            auth_response=auth_response,
        )

        if "access_token" not in result:
            error = result.get("error", "unknown")
            description = result.get("error_description", "No description")
            logger.error("Token acquisition failed: %s - %s", error, description)
            return None

        expires_in = result.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        return TokenResult(
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token"),
            expires_at=expires_at,
            id_token_claims=result.get("id_token_claims", {}),
        )

    def refresh_access_token(self, refresh_token: str) -> TokenResult | None:
        """Refresh an expired access token.

        Parameters
        ----------
        refresh_token : str
            The refresh token to use.

        Returns
        -------
        TokenResult or None
            New token result if successful, None otherwise.
        """
        result = self._app.acquire_token_by_refresh_token(
            refresh_token=refresh_token,
            scopes=self._settings.microsoft_scopes,
        )

        if "access_token" not in result:
            error = result.get("error", "unknown")
            logger.error("Token refresh failed: %s", error)
            return None

        expires_in = result.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        return TokenResult(
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token", refresh_token),
            expires_at=expires_at,
            id_token_claims=result.get("id_token_claims", {}),
        )


_auth_service: MicrosoftAuthService | None = None


def get_microsoft_auth_service() -> MicrosoftAuthService:
    """Get the Microsoft authentication service singleton.

    Returns
    -------
    MicrosoftAuthService
        The authentication service instance.
    """
    global _auth_service
    if _auth_service is None:
        _auth_service = MicrosoftAuthService()
    return _auth_service
