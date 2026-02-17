from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.db.models import Job, JobAttempt
from backend.services.jobs import JobService


@pytest.mark.asyncio
async def test_delete_job_allows_finalized_status():
    session = AsyncMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="COMPLETED")
    session.get.return_value = job

    service = JobService(session)
    await service.delete_job(job_id)

    session.delete.assert_awaited_once_with(job)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_job_rejects_running_status():
    session = AsyncMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="RUNNING")
    session.get.return_value = job

    service = JobService(session)

    with pytest.raises(ValueError):
        await service.delete_job(job_id)


@pytest.mark.asyncio
async def test_request_cancel_pending_job_marks_cancelled():
    session = AsyncMock()
    session.add = MagicMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="PENDING")
    session.get.return_value = job

    service = JobService(session)
    result = await service.request_cancel(job_id)

    assert result.status == "CANCELLED"
    assert result.result["cancelled"] is True
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_request_cancel_running_job_marks_cancelled():
    session = AsyncMock()
    session.add = MagicMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="RUNNING")
    session.get.return_value = job

    service = JobService(session)
    result = await service.request_cancel(job_id)

    assert result.status == "CANCELLED"
    assert result.result["cancelled"] is True
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_delete_job_allows_cancelled_status():
    session = AsyncMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="CANCELLED")
    session.get.return_value = job

    service = JobService(session)
    await service.delete_job(job_id)

    session.delete.assert_awaited_once_with(job)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_jobs_reads_without_reconciliation_write():
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    service = JobService(session)
    jobs = await service.get_jobs()

    assert jobs == []
    session.execute.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reprocess_job_clones_finalized_job():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    source_id = uuid4()
    new_id = uuid4()
    source = Job(
        id=source_id,
        type="sync_items",
        status="DEAD_LETTER",
        payload={"account_id": "acc-1"},
        max_retries=5,
    )
    session.get.return_value = source

    async def _refresh(job):
        if getattr(job, "id", None) is None:
            job.id = new_id

    session.refresh.side_effect = _refresh

    service = JobService(session, queue=queue)
    created = await service.reprocess_job(source_id)

    assert created.id == new_id
    assert created.reprocessed_from_job_id == source_id
    queue.enqueue_job.assert_awaited_once_with(str(new_id))


@pytest.mark.asyncio
async def test_get_job_attempts_returns_rows():
    session = AsyncMock()
    service = JobService(session)
    job_id = uuid4()
    session.scalar.return_value = 1
    result = MagicMock()
    attempt = JobAttempt(id=uuid4(), job_id=job_id, attempt_number=1, status="COMPLETED", triggered_by="worker")
    result.scalars.return_value.all.return_value = [attempt]
    session.execute.return_value = result

    rows = await service.get_job_attempts(job_id, limit=5)

    assert len(rows) == 1
    assert rows[0].job_id == job_id
