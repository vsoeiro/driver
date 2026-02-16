from unittest.mock import AsyncMock
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
