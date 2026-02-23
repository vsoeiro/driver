"""API dependencies for FastAPI dependency injection.

This module provides common dependencies like database sessions
and current user authentication.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LinkedAccount
from backend.db.session import async_session_maker, get_db
from backend.services.jobs import JobService
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager

DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session.
    
    Returns
    -------
    AsyncSession
        Database session.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_linked_account(
    account_id: str,
    db: DBSession,
) -> LinkedAccount:
    """Get a linked account by ID.
    
    Parameters
    ----------
    account_id : str
        The linked account ID.
    db : AsyncSession
        Database session.

    Returns
    -------
    LinkedAccount
        The linked account.

    Raises
    ------
    HTTPException
        If the account is not found.
    """
    query = select(LinkedAccount).where(LinkedAccount.id == uuid.UUID(account_id))
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    return account


LinkedAccountDep = Annotated[LinkedAccount, Depends(get_linked_account)]


def get_token_manager(db: DBSession) -> TokenManager:
    """Get a token manager instance.

    Parameters
    ----------
    db : AsyncSession
        Database session.

    Returns
    -------
    TokenManager
        Token manager instance.
    """
    return TokenManager(db)


TokenManagerDep = Annotated[TokenManager, Depends(get_token_manager)]


def get_drive_client(account: LinkedAccountDep, db: DBSession) -> DriveProviderClient:
    """Get a provider-specific drive client instance.

    Parameters
    ----------
    account : LinkedAccount
        The linked account whose provider defines the client implementation.
    db : AsyncSession
        Database session for token lifecycle operations.

    Returns
    -------
    DriveProviderClient
        Provider-specific drive client instance.
    """
    token_manager = TokenManager(db)
    return build_drive_client(account, token_manager)


DriveClientDep = Annotated[DriveProviderClient, Depends(get_drive_client)]


def get_job_service(db: DBSession) -> JobService:
    """Get a job service instance.

    Parameters
    ----------
    db : AsyncSession
        Database session.

    Returns
    -------
    JobService
        Job service instance.
    """
    return JobService(db)


JobServiceDep = Annotated[JobService, Depends(get_job_service)]
