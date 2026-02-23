from uuid import uuid4

import pytest

from backend.core.exceptions import DriveOrganizerError
from backend.db.models import LinkedAccount
from backend.services.google_drive_client import GoogleDriveClient
from backend.services.graph_client import GraphClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager


def _make_account(provider: str) -> LinkedAccount:
    return LinkedAccount(
        id=uuid4(),
        provider=provider,
        provider_account_id=f"{provider}-acct",
        email=f"{provider}@example.com",
        display_name=f"{provider} user",
        access_token_encrypted="enc",
        refresh_token_encrypted="enc",
        token_expires_at=None,
        is_active=True,
    )


def test_build_drive_client_microsoft():
    account = _make_account("microsoft")
    token_manager = TokenManager(None)  # type: ignore[arg-type]
    client = build_drive_client(account, token_manager)
    assert isinstance(client, GraphClient)


def test_build_drive_client_google():
    account = _make_account("google")
    token_manager = TokenManager(None)  # type: ignore[arg-type]
    client = build_drive_client(account, token_manager)
    assert isinstance(client, GoogleDriveClient)


def test_build_drive_client_unsupported_provider():
    account = _make_account("dropbox")
    token_manager = TokenManager(None)  # type: ignore[arg-type]

    with pytest.raises(DriveOrganizerError) as exc:
        build_drive_client(account, token_manager)

    assert exc.value.status_code == 501
