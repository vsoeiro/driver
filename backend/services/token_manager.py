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
from backend.services.microsoft_auth import get_microsoft_auth_service

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
        self._auth_service = get_microsoft_auth_service()

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
            if token:
                return token

        return await self._refresh_token(account)

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

    async def _refresh_token(self, account: LinkedAccount) -> str:
        """Refresh the access token for an account.

        Parameters
        ----------
        account : LinkedAccount
            The linked account to refresh.

        Returns
        -------
        str
            The new access token.

        Raises
        ------
        TokenRefreshError
            If refresh fails.
        """
        # Use select with_for_update to lock the row and prevent race conditions
        from sqlalchemy import select
        
        # Start a new transaction or use existing one to lock the row
        # This prevents other concurrent requests from refreshing the same token
        stmt = select(LinkedAccount).where(LinkedAccount.id == account.id).with_for_update()
        result = await self._db.execute(stmt)
        locked_account = result.scalar_one()

        # Check if validity again - maybe another process just refreshed it
        if self._is_token_valid(locked_account):
             logger.info("Token was already refreshed by another process")
             token = decrypt_token(locked_account.access_token_encrypted)
             if token:
                 # Update the passed account object in memory to match DB
                 account.access_token_encrypted = locked_account.access_token_encrypted
                 account.refresh_token_encrypted = locked_account.refresh_token_encrypted
                 account.token_expires_at = locked_account.token_expires_at
                 return token

        if not locked_account.refresh_token_encrypted:
            logger.error("No refresh token available for account %s", locked_account.id)
            await self._mark_account_inactive(locked_account)
            raise TokenRefreshError("No refresh token available")

        refresh_token = decrypt_token(locked_account.refresh_token_encrypted)
        if not refresh_token:
            logger.error("Failed to decrypt refresh token for account %s", locked_account.id)
            await self._mark_account_inactive(locked_account)
            raise TokenRefreshError("Failed to decrypt refresh token")

        result = self._auth_service.refresh_access_token(refresh_token)
        if not result:
            logger.error(
                "Token refresh failed for account %s. Result was None. Refresh token (masked): %s...",
                locked_account.id,
                refresh_token[:10] if refresh_token else "None"
            )
            logger.error("Token refresh failed for account %s", locked_account.id)
            await self._mark_account_inactive(locked_account)
            raise TokenRefreshError("Token refresh failed")

        locked_account.access_token_encrypted = encrypt_token(result.access_token)
        if result.refresh_token:
            locked_account.refresh_token_encrypted = encrypt_token(result.refresh_token)
        locked_account.token_expires_at = result.expires_at

        # Update the original object reference too
        account.access_token_encrypted = locked_account.access_token_encrypted
        account.refresh_token_encrypted = locked_account.refresh_token_encrypted
        account.token_expires_at = locked_account.token_expires_at

        await self._db.commit()
        logger.info("Successfully refreshed token for account %s", locked_account.id)

        return result.access_token

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
