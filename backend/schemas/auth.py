"""Authentication schemas.

Pydantic models for authentication-related API requests and responses.
"""

from pydantic import BaseModel, Field


class AuthURLResponse(BaseModel):
    """Response containing the Microsoft OAuth login URL.

    Attributes
    ----------
    auth_url : str
        The Microsoft OAuth authorization URL.
    state : str
        CSRF protection state parameter.
    """

    auth_url: str = Field(..., description="Microsoft OAuth authorization URL")
    state: str = Field(..., description="CSRF state parameter")


class TokenResponse(BaseModel):
    """Response containing the application JWT token.

    Attributes
    ----------
    access_token : str
        The application JWT token.
    token_type : str
        Token type, always 'bearer'.
    """

    access_token: str = Field(..., description="Application JWT token")
    token_type: str = Field(default="bearer", description="Token type")


class UserInfo(BaseModel):
    """Current user information.

    Attributes
    ----------
    id : str
        User ID.
    email : str
        User email address.
    name : str
        User display name.
    """

    id: str
    email: str
    name: str
