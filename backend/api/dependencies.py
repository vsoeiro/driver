"""API dependencies for FastAPI dependency injection.

This module provides common dependencies like database sessions
and current user authentication.
"""

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.security import decode_jwt_token
from backend.db.models import LinkedAccount, User
from backend.db.session import get_db
from backend.services.graph_client import GraphClient
from backend.services.token_manager import TokenManager

DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DBSession,
    session_token: Annotated[str | None, Cookie()] = None,
) -> User:
    """Get the currently authenticated user from session cookie.

    Parameters
    ----------
    db : AsyncSession
        Database session.
    session_token : str, optional
        JWT session token from cookie.

    Returns
    -------
    User
        The authenticated user.

    Raises
    ------
    HTTPException
        If authentication fails.
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_jwt_token(session_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    query = (
        select(User)
        .where(User.id == uuid.UUID(user_id))
        .options(selectinload(User.linked_accounts))
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_linked_account(
    account_id: str,
    db: DBSession,
    current_user: CurrentUser,
) -> LinkedAccount:
    """Get a linked account by ID, ensuring it belongs to the current user.

    Parameters
    ----------
    account_id : str
        The linked account ID.
    db : AsyncSession
        Database session.
    current_user : User
        The authenticated user.

    Returns
    -------
    LinkedAccount
        The linked account.

    Raises
    ------
    HTTPException
        If the account is not found or doesn't belong to the user.
    """
    query = select(LinkedAccount).where(
        LinkedAccount.id == uuid.UUID(account_id),
        LinkedAccount.user_id == current_user.id,
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please re-authenticate.",
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
