from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.db.models import Job
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
