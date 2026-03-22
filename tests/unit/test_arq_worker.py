from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.workers import arq_worker


@pytest.mark.asyncio
async def test_process_job_completes_successfully(monkeypatch):
    job_id = uuid4()
    fake_job = SimpleNamespace(
        id=job_id,
        type="sync_items",
        status="RUNNING",
        payload={"account_id": "x"},
        _claimed_by_worker=True,
    )

    class FakeJobService:
        def __init__(self, session):
            self.start_job = AsyncMock(return_value=fake_job)
            self.is_cancel_requested = AsyncMock(return_value=False)
            self.complete_job = AsyncMock()
            self.cancel_running_job = AsyncMock()
            self.fail_job = AsyncMock()

    fake_service = FakeJobService(None)

    @asynccontextmanager
    async def fake_session_maker():
        yield AsyncMock()

    async def fake_handler(payload, session):
        return {"ok": True}

    monkeypatch.setattr(arq_worker, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(arq_worker, "JobService", lambda session: fake_service)
    monkeypatch.setattr(arq_worker, "get_handler", lambda _job_type: fake_handler)

    await arq_worker.process_job({}, str(job_id))

    fake_service.start_job.assert_awaited_once_with(job_id)
    fake_service.complete_job.assert_awaited_once()
    args, _kwargs = fake_service.complete_job.await_args
    assert args[0] == job_id
    assert "metrics" in args[1]


@pytest.mark.asyncio
async def test_process_job_retries_on_handler_error(monkeypatch):
    job_id = uuid4()
    fake_job = SimpleNamespace(
        id=job_id,
        type="sync_items",
        status="RUNNING",
        payload={"account_id": "x"},
        _claimed_by_worker=True,
    )

    class FakeJobService:
        def __init__(self, session):
            self.start_job = AsyncMock(return_value=fake_job)
            self.is_cancel_requested = AsyncMock(return_value=False)
            self.complete_job = AsyncMock()
            self.cancel_running_job = AsyncMock()
            self.fail_job = AsyncMock()

    fake_service = FakeJobService(None)

    @asynccontextmanager
    async def fake_session_maker():
        yield AsyncMock()

    async def failing_handler(payload, session):
        raise RuntimeError("boom")

    monkeypatch.setattr(arq_worker, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(arq_worker, "JobService", lambda session: fake_service)
    monkeypatch.setattr(arq_worker, "get_handler", lambda _job_type: failing_handler)

    await arq_worker.process_job({}, str(job_id))

    fake_service.fail_job.assert_awaited_once()
    args, _kwargs = fake_service.fail_job.await_args
    assert args[0] == job_id
    assert "boom" in args[1]


@pytest.mark.asyncio
async def test_process_job_skips_when_message_was_already_claimed_elsewhere(monkeypatch):
    job_id = uuid4()
    fake_job = SimpleNamespace(
        id=job_id,
        type="sync_items",
        status="RUNNING",
        payload={"account_id": "x"},
        _claimed_by_worker=False,
    )

    class FakeJobService:
        def __init__(self, session):
            self.start_job = AsyncMock(return_value=fake_job)
            self.is_cancel_requested = AsyncMock(return_value=False)
            self.complete_job = AsyncMock()
            self.cancel_running_job = AsyncMock()
            self.fail_job = AsyncMock()

    fake_service = FakeJobService(None)

    @asynccontextmanager
    async def fake_session_maker():
        yield AsyncMock()

    async def fake_handler(payload, session):
        return {"ok": True}

    monkeypatch.setattr(arq_worker, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(arq_worker, "JobService", lambda session: fake_service)
    monkeypatch.setattr(arq_worker, "get_handler", lambda _job_type: fake_handler)

    await arq_worker.process_job({}, str(job_id))

    fake_service.complete_job.assert_not_awaited()
    fake_service.fail_job.assert_not_awaited()
