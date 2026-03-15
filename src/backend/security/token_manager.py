"""Token manager service.

This module manages OAuth token lifecycle including automatic refresh
and secure storage/retrieval of encrypted tokens.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import TokenRefreshError
from backend.core.security import decrypt_token, encrypt_token
from backend.db.models import LinkedAccount
from backend.security.oauth_types import AuthServiceProtocol
from backend.services.dropbox.auth import get_dropbox_auth_service
from backend.services.google.auth import get_google_auth_service
from backend.services.microsoft.auth import get_microsoft_auth_service

logger = logging.getLogger(__name__)

TOKEN_REFRESH_MARGIN = timedelta(minutes=5)


class TokenManager:
    """Manages OAuth token lifecycle for linked accounts.

    Handles token encryption, decryption, refresh, and validation.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the token manager.

        Parameters
        ----------
        db : AsyncSession
            Database session for token operations.

        """
        self._db = db
        self._microsoft_auth_service = get_microsoft_auth_service()
        self._google_auth_service = get_google_auth_service()
        self._dropbox_auth_service = get_dropbox_auth_service()

    async def get_valid_access_token(self, account: LinkedAccount) -> str:
        """Get a valid access token for the account, refreshing if needed.

        Parameters
        ----------
        account : LinkedAccount
            The linked account to get the token for.

        Returns
        -------
        str
            A valid access token.

        Raises
        ------
        TokenRefreshError
            If the token cannot be refreshed.

        """
        if self._is_token_valid(account):
            token = decrypt_token(account.access_token_encrypted)
            if token and self._looks_like_valid_access_token(account.provider, token):
                return token
            if token:
                logger.warning(
                    "Detected malformed cached access token for account %s (provider=%s). Forcing refresh.",
                    account.id,
                    account.provider,
                )
                return await self._refresh_token(account, force=True)

        return await self._refresh_token(account)

    async def force_refresh_access_token(self, account: LinkedAccount) -> str:
        """Force refresh access token regardless of cached token validity."""
        return await self._refresh_token(account, force=True)

    def _is_token_valid(self, account: LinkedAccount) -> bool:
        """Check if the account's access token is still valid.

        Parameters
        ----------
        account : LinkedAccount
            The linked account to check.

        Returns
        -------
        bool
            True if the token is valid and not expired.

        """
        if not account.token_expires_at:
            return False

        if account.token_expires_at.tzinfo is None:
            account.token_expires_at = account.token_expires_at.replace(tzinfo=UTC)

        expiry_threshold = datetime.now(UTC) + TOKEN_REFRESH_MARGIN
        return account.token_expires_at > expiry_threshold

    async def _refresh_token(self, account: LinkedAccount, force: bool = False) -> str:
        """Refresh the access token for an account.

        Parameters
        ----------
        account : LinkedAccount
            The linked account to refresh.
        force : bool, optional
            Whether to force refresh even if the cached token is still valid.

        Returns
        -------
        str
            The new access token.

        Raises
        ------
        TokenRefreshError
            If refresh fails.

        """
        from sqlalchemy import select

        # Lock the row to prevent concurrent refresh attempts for the same account.
        stmt = select(LinkedAccount).where(LinkedAccount.id == account.id).with_for_update()
        result = await self._db.execute(stmt)
        locked_account = result.scalar_one()

        # Another process may have refreshed the token while we waited on the lock.
        if not force and self._is_token_valid(locked_account):
            logger.info("Token was already refreshed by another process")
            token = decrypt_token(locked_account.access_token_encrypted)
            if token and self._looks_like_valid_access_token(locked_account.provider, token):
                account.access_token_encrypted = locked_account.access_token_encrypted
                account.refresh_token_encrypted = locked_account.refresh_token_encrypted
                account.token_expires_at = locked_account.token_expires_at
                return token

        if not locked_account.refresh_token_encrypted:
            logger.error("No refresh token available for account %s", locked_account.id)
            await self._mark_account_inactive(locked_account)
            raise TokenRefreshError("No refresh token available", deactivate_account=True)

        refresh_token = decrypt_token(locked_account.refresh_token_encrypted)
        if not refresh_token:
            logger.error("Failed to decrypt refresh token for account %s", locked_account.id)
            await self._mark_account_inactive(locked_account)
            raise TokenRefreshError("Failed to decrypt refresh token", deactivate_account=True)

        auth_service = self._get_auth_service(locked_account.provider)
        try:
            refreshed_tokens = await auth_service.refresh_access_token(refresh_token)
            if not refreshed_tokens:
                raise TokenRefreshError(
                    f"{locked_account.provider} token refresh returned no token data"
                )

            locked_account.access_token_encrypted = encrypt_token(refreshed_tokens.access_token)
            if refreshed_tokens.refresh_token:
                locked_account.refresh_token_encrypted = encrypt_token(
                    refreshed_tokens.refresh_token
                )
            locked_account.token_expires_at = refreshed_tokens.expires_at

            account.access_token_encrypted = locked_account.access_token_encrypted
            account.refresh_token_encrypted = locked_account.refresh_token_encrypted
            account.token_expires_at = locked_account.token_expires_at

            await self._db.commit()
            logger.info("Successfully refreshed token for account %s", locked_account.id)
            return refreshed_tokens.access_token
        except TokenRefreshError as exc:
            logger.error(
                "Token refresh failed for account %s (provider=%s): %s",
                locked_account.id,
                locked_account.provider,
                exc.message,
            )
            if exc.deactivate_account:
                await self._mark_account_inactive(locked_account)
            else:
                await self._db.rollback()
            raise
        except Exception:
            await self._db.rollback()
            raise

    def _looks_like_valid_access_token(self, provider: str, token: str) -> bool:
        value = (token or "").strip()
        if not value:
            return False

        provider_key = (provider or "").lower()
        if provider_key == "microsoft":
            # Some valid MSAL-issued Microsoft tokens may not be plain JWT strings
            # depending on authority/tenant flow; only reject obviously broken values.
            if " " in value or "\n" in value or "\r" in value:
                return False
            return len(value) >= 20

        # Google access tokens can be opaque, so only basic sanity checks apply.
        return True

    def _get_auth_service(self, provider: str) -> AuthServiceProtocol:
        provider_key = (provider or "").lower()
        if provider_key == "microsoft":
            return self._microsoft_auth_service
        if provider_key == "google":
            return self._google_auth_service
        if provider_key == "dropbox":
            return self._dropbox_auth_service
        raise TokenRefreshError(f"Unsupported provider for token refresh: {provider}")

    async def _mark_account_inactive(self, account: LinkedAccount) -> None:
        """Mark an account as inactive due to authentication failure.

        Parameters
        ----------
        account : LinkedAccount
            The account to mark as inactive.

        """
        account.is_active = False
        await self._db.commit()
        logger.warning("Marked account %s as inactive", account.id)

    async def store_tokens(
        self,
        account: LinkedAccount,
        access_token: str,
        refresh_token: str | None,
        expires_at: datetime,
    ) -> None:
        """Store encrypted tokens for an account.

        Parameters
        ----------
        account : LinkedAccount
            The account to store tokens for.
        access_token : str
            The access token to encrypt and store.
        refresh_token : str, optional
            The refresh token to encrypt and store.
        expires_at : datetime
            Token expiration timestamp.

        """
        account.access_token_encrypted = encrypt_token(access_token)
        if refresh_token:
            account.refresh_token_encrypted = encrypt_token(refresh_token)
        account.token_expires_at = expires_at
        account.is_active = True
        await self._db.commit()

