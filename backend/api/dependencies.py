"""API dependencies for FastAPI dependency injection.

This module provides common dependencies like database sessions
and current user authentication.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LinkedAccount
from backend.db.session import get_db
from backend.services.graph_client import GraphClient
from backend.services.jobs import JobService
from backend.services.token_manager import TokenManager

DBSession = Annotated[AsyncSession, Depends(get_db)]


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


def get_graph_client(token_manager: TokenManagerDep) -> GraphClient:
    """Get a Graph API client instance.

    Parameters
    ----------
    token_manager : TokenManager
        Token manager for authentication.

    Returns
    -------
    GraphClient
        Graph API client instance.
    """
    return GraphClient(token_manager)


GraphClientDep = Annotated[GraphClient, Depends(get_graph_client)]


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
