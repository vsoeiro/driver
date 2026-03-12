from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.api.routes import accounts as accounts_routes


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


@pytest.mark.asyncio
async def test_list_linked_accounts_maps_database_rows():
    account = SimpleNamespace(
        id=uuid4(),
        email="reader@example.com",
        display_name="Reader",
        provider="onedrive",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_FakeResult([account])),
    )

    response = await accounts_routes.list_linked_accounts(db)

    assert response.total == 1
    assert response.accounts[0].email == "reader@example.com"
    assert response.accounts[0].provider == "onedrive"
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_linked_account_maps_dependency_model():
    account = SimpleNamespace(
        id=uuid4(),
        email="reader@example.com",
        display_name="Reader",
        provider="google",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    response = await accounts_routes.get_linked_account(account)

    assert response.id == str(account.id)
    assert response.display_name == "Reader"
    assert response.provider == "google"


@pytest.mark.asyncio
async def test_disconnect_account_deletes_and_commits():
    account = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(delete=AsyncMock(), commit=AsyncMock())

    assert await accounts_routes.disconnect_account(account, db) is None

    db.delete.assert_awaited_once_with(account)
    db.commit.assert_awaited_once_with()
