"""Account management routes.

This module provides endpoints for managing linked Microsoft accounts.
"""

import logging

from fastapi import APIRouter, status

from backend.api.dependencies import CurrentUser, DBSession, LinkedAccountDep
from backend.schemas.account import LinkedAccountList, LinkedAccountResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("", response_model=LinkedAccountList)
async def list_linked_accounts(
    db: DBSession,
    current_user: CurrentUser,
) -> LinkedAccountList:
    """List linked Microsoft accounts for the authenticated user.

    Parameters
    ----------
    db : AsyncSession
        Database session.

    Returns
    -------
    LinkedAccountList
        List of linked accounts for the authenticated user.
    """
    from sqlalchemy import select
    from backend.db.models import LinkedAccount

    result = await db.execute(
        select(LinkedAccount).where(
            LinkedAccount.user_id == current_user.id,
            LinkedAccount.is_active.is_(True),
        )
    )
    all_accounts = result.scalars().all()

    accounts = [
        LinkedAccountResponse(
            id=str(account.id),
            email=account.email,
            display_name=account.display_name,
            provider=account.provider,
            is_active=account.is_active,
            created_at=account.created_at,
        )
        for account in all_accounts
    ]

    return LinkedAccountList(accounts=accounts, total=len(accounts))


@router.get("/{account_id}", response_model=LinkedAccountResponse)
async def get_linked_account(account: LinkedAccountDep) -> LinkedAccountResponse:
    """Get a specific linked account by ID.

    Parameters
    ----------
    account : LinkedAccount
        The linked account (injected by dependency).

    Returns
    -------
    LinkedAccountResponse
        Account details.
    """
    return LinkedAccountResponse(
        id=str(account.id),
        email=account.email,
        display_name=account.display_name,
        provider=account.provider,
        is_active=account.is_active,
        created_at=account.created_at,
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_account(
    account: LinkedAccountDep,
    db: DBSession,
) -> None:
    """Disconnect (delete) a linked Microsoft account.

    Parameters
    ----------
    account : LinkedAccount
        The linked account to disconnect.
    db : AsyncSession
        Database session.
    """
    await db.delete(account)
    await db.commit()
    logger.info("Disconnected account %s", account.id)
