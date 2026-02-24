from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.db.models import Job
from backend.schemas.jobs import JobCreate
from backend.services.jobs import JobService


@pytest.mark.asyncio
async def test_create_job_enqueues_in_redis_queue():
    session = AsyncMock()
    session.add = MagicMock()
    no_duplicate = MagicMock()
    no_duplicate.scalar_one_or_none.return_value = None
    session.execute.return_value = no_duplicate
    queue = AsyncMock()

    generated_id = uuid4()

    async def _refresh(job):
        job.id = generated_id

    session.refresh.side_effect = _refresh

    service = JobService(session, queue=queue)
    created = await service.create_job(JobCreate(type="sync_items", payload={"account_id": "x"}))

    assert created.id == generated_id
    queue.enqueue_job.assert_awaited_once()
    args, kwargs = queue.enqueue_job.await_args
    assert args[0] == str(generated_id)
    assert isinstance(kwargs.get("queue_name"), str)
    assert kwargs.get("queue_name")


@pytest.mark.asyncio
async def test_fail_job_retry_reenqueues_with_backoff():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    job_id = uuid4()
    job = Job(
        id=job_id,
        type="sync_items",
        status="RUNNING",
        payload={},
        retry_count=0,
        max_retries=3,
        created_at=datetime.now(UTC),
    )
    session.get.return_value = job

    service = JobService(session, queue=queue)
    await service.fail_job(job_id, "boom")

    assert job.status == "RETRY_SCHEDULED"
    queue.enqueue_job.assert_awaited_once()
    args, kwargs = queue.enqueue_job.await_args
    assert args[0] == str(job_id)
    assert kwargs["defer_seconds"] >= 1
    assert isinstance(kwargs.get("queue_name"), str)
    assert kwargs.get("queue_name")


@pytest.mark.asyncio
async def test_fail_job_dead_letter_does_not_enqueue():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    job_id = uuid4()
    job = Job(
        id=job_id,
        type="sync_items",
        status="RUNNING",
        payload={},
        retry_count=3,
        max_retries=3,
        created_at=datetime.now(UTC),
    )
    session.get.return_value = job

    service = JobService(session, queue=queue)
    await service.fail_job(job_id, "boom")

    assert job.status == "DEAD_LETTER"
    queue.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_job_dedupe_returns_existing_active_job():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    duplicate_id = uuid4()
    duplicate = Job(
        id=duplicate_id,
        type="sync_items",
        status="PENDING",
        payload={"account_id": "x"},
        queue_name="driver:jobs:sync",
        max_retries=2,
        created_at=datetime.now(UTC),
    )
    found_duplicate = MagicMock()
    found_duplicate.scalar_one_or_none.return_value = duplicate
    session.execute.return_value = found_duplicate

    service = JobService(session, queue=queue)
    result = await service.create_job(JobCreate(type="sync_items", payload={"account_id": "x"}))

    assert result.id == duplicate_id
    session.commit.assert_not_awaited()
    queue.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_job_applies_type_policy_when_not_explicit(monkeypatch):
    settings = SimpleNamespace(
        redis_queue_name="driver:jobs",
        job_queue_names={},
        job_type_queue_map={},
        job_type_max_retries_map={},
        job_default_max_retries=3,
        worker_concurrency=8,
        worker_job_timeout_seconds=1800,
    )
    monkeypatch.setattr("backend.services.jobs.get_settings", lambda: settings)

    session = AsyncMock()
    session.add = MagicMock()
    no_duplicate = MagicMock()
    no_duplicate.scalar_one_or_none.return_value = None
    session.execute.return_value = no_duplicate
    queue = AsyncMock()
    generated_id = uuid4()

    async def _refresh(job):
        job.id = generated_id

    session.refresh.side_effect = _refresh

    service = JobService(session, queue=queue)
    created = await service.create_job(JobCreate(type="sync_items", payload={"account_id": "acc-1"}))

    assert created.max_retries == 2
    assert created.queue_name == "driver:jobs:light"
