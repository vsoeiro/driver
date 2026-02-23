from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.api.routes.jobs import cancel_job, delete_job, list_job_attempts, reprocess_job
from backend.domain.errors import NotFoundError, ValidationError


class _NotFoundJobService:
    async def delete_job(self, _job_id):
        raise NotFoundError("Job not found")

    async def get_job_attempts(self, _job_id, limit=20):  # noqa: ARG002
        raise NotFoundError("Job not found")


class _ValidationJobService:
    async def request_cancel(self, _job_id):
        raise ValidationError("Finalized jobs cannot be cancelled")

    async def reprocess_job(self, _job_id):
        raise ValidationError("Only finalized jobs can be reprocessed")


@pytest.mark.asyncio
async def test_jobs_api_maps_not_found_to_404():
    job_id = uuid4()
    service = _NotFoundJobService()

    with pytest.raises(HTTPException) as delete_exc:
        await delete_job(job_id, service)  # type: ignore[arg-type]
    assert delete_exc.value.status_code == 404

    with pytest.raises(HTTPException) as attempts_exc:
        await list_job_attempts(job_id, service, limit=20)  # type: ignore[arg-type]
    assert attempts_exc.value.status_code == 404


@pytest.mark.asyncio
async def test_jobs_api_maps_validation_to_400():
    job_id = uuid4()
    service = _ValidationJobService()

    with pytest.raises(HTTPException) as cancel_exc:
        await cancel_job(job_id, service)  # type: ignore[arg-type]
    assert cancel_exc.value.status_code == 400

    with pytest.raises(HTTPException) as reprocess_exc:
        await reprocess_job(job_id, service)  # type: ignore[arg-type]
    assert reprocess_exc.value.status_code == 400
