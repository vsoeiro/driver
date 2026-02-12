"""Account schemas.

Pydantic models for linked account API requests and responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class LinkedAccountResponse(BaseModel):
    """Response for a linked Microsoft account.

    Attributes
    ----------
    id : str
        Linked account ID.
    email : str
        Account email address.
    display_name : str
        Account display name.
    provider : str
        OAuth provider name.
    is_active : bool
        Whether the account is currently active.
    created_at : datetime
        When the account was linked.
    """

    id: str
    email: str
    display_name: str
    provider: str
    is_active: bool
    created_at: datetime


class LinkedAccountList(BaseModel):
    """Response containing list of linked accounts.

    Attributes
    ----------
    accounts : list[LinkedAccountResponse]
        List of linked accounts.
    total : int
        Total number of linked accounts.
    """

    accounts: list[LinkedAccountResponse] = Field(default_factory=list)
    total: int = Field(..., description="Total number of linked accounts")
