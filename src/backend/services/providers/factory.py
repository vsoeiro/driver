"""Drive provider factory."""

from __future__ import annotations

from backend.core.exceptions import DriveOrganizerError
from backend.db.models import LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.google.drive.client import GoogleDriveClient
from backend.services.microsoft.onedrive.client import GraphClient
from backend.services.providers.base import DriveProviderClient


def build_drive_client(
    account: LinkedAccount, token_manager: TokenManager
) -> DriveProviderClient:
    """Return the provider-specific drive client for an account."""
    provider = (account.provider or "").lower()

    if provider == "microsoft":
        return GraphClient(token_manager)
    if provider == "google":
        return GoogleDriveClient(token_manager)

    raise DriveOrganizerError(
        f"Provider '{account.provider}' is not supported yet",
        status_code=501,
    )
