"""Custom application exceptions.

This module defines application-specific exceptions for better
error handling and API responses.
"""


class DriveOrganizerError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        """Initialize the exception.

        Parameters
        ----------
        message : str
            Error message.
        status_code : int, optional
            HTTP status code. Defaults to 500.
        """
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(DriveOrganizerError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        """Initialize authentication error.

        Parameters
        ----------
        message : str, optional
            Error message. Defaults to "Authentication failed".
        """
        super().__init__(message, status_code=401)


class AuthorizationError(DriveOrganizerError):
    """Raised when user lacks permission."""

    def __init__(self, message: str = "Access denied") -> None:
        """Initialize authorization error.

        Parameters
        ----------
        message : str, optional
            Error message. Defaults to "Access denied".
        """
        super().__init__(message, status_code=403)


class AccountNotFoundError(DriveOrganizerError):
    """Raised when a linked account is not found."""

    def __init__(self, account_id: str) -> None:
        """Initialize account not found error.

        Parameters
        ----------
        account_id : str
            The account ID that was not found.
        """
        super().__init__(f"Account {account_id} not found", status_code=404)


class TokenRefreshError(DriveOrganizerError):
    """Raised when token refresh fails."""

    def __init__(
        self,
        message: str = "Failed to refresh access token",
        *,
        deactivate_account: bool = False,
    ) -> None:
        """Initialize token refresh error.

        Parameters
        ----------
        message : str, optional
            Error message.
        deactivate_account : bool, optional
            Whether the linked account should be marked inactive because the
            refresh token is no longer usable.
        """
        self.deactivate_account = deactivate_account
        super().__init__(message, status_code=401)


class GraphAPIError(DriveOrganizerError):
    """Raised when Microsoft Graph API call fails."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        """Initialize Graph API error.

        Parameters
        ----------
        message : str
            Error message from Graph API.
        status_code : int, optional
            HTTP status code. Defaults to 502.
        """
        super().__init__(f"Graph API error: {message}", status_code=status_code)
