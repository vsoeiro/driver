"""Application commands for background job orchestration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.jobs.types import JobType, normalize_job_type
from backend.schemas.jobs import JobCreate
from backend.services.jobs import JobService


async def enqueue_job_command(
    session: AsyncSession,
    *,
    job_type: JobType | str,
    payload: dict[str, Any],
    max_retries: int | None = None,
    queue_name: str | None = None,
    dedupe_key: str | None = None,
    reprocessed_from_job_id: UUID | None = None,
) -> Any:
    """Create and enqueue one job using centralized service/policies."""
    job_service = JobService(session)
    job_in = JobCreate(
        type=normalize_job_type(job_type),
        payload=payload,
        max_retries=max_retries,
        queue_name=queue_name,
        dedupe_key=dedupe_key,
    )
    return await job_service.create_job(job_in, reprocessed_from_job_id=reprocessed_from_job_id)

