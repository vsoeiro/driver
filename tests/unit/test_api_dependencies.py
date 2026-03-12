import types
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.api import dependencies


@pytest.mark.asyncio
async def test_get_session_rolls_back_on_error(monkeypatch):
    session = SimpleNamespace(rollback=AsyncMock())

    @asynccontextmanager
    async def fake_session_maker():
        yield session

    monkeypatch.setattr(dependencies, "async_session_maker", fake_session_maker)

    generator = dependencies.get_session()
    yielded = await anext(generator)
    assert yielded is session

    with pytest.raises(RuntimeError):
        await generator.athrow(RuntimeError("boom"))

    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_get_linked_account_returns_account_and_404s():
    account = SimpleNamespace(id=uuid4())
    found_db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: account))
    )
    missing_db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )

    result = await dependencies.get_linked_account(str(account.id), found_db)
    assert result is account

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_linked_account(str(uuid4()), missing_db)

    assert exc.value.status_code == 404


def test_factory_dependencies_create_expected_objects(monkeypatch):
    token_manager = object()
    job_service = object()
    drive_client = object()
    monkeypatch.setattr(dependencies, "TokenManager", lambda db: token_manager)
    monkeypatch.setattr(dependencies, "JobService", lambda db: job_service)
    monkeypatch.setattr(dependencies, "build_drive_client", lambda account, manager: (drive_client, account, manager))

    db = object()
    account = object()

    assert dependencies.get_token_manager(db) is token_manager
    assert dependencies.get_job_service(db) is job_service
    assert dependencies.get_drive_client(account, db) == (drive_client, account, token_manager)
