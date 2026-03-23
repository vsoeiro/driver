"""Application commands for background job orchestration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.domain.errors import ValidationError
from backend.domain.jobs.types import JobType, normalize_job_type
from backend.schemas.jobs import JobCreate
from backend.services.jobs import JobService

IMAGE_ANALYSIS_JOB_TYPES = {
    JobType.ANALYZE_IMAGE_ASSETS.value,
    JobType.ANALYZE_LIBRARY_IMAGE_ASSETS.value,
}


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
    normalized_job_type = normalize_job_type(job_type)
    settings = get_settings()
    if normalized_job_type in IMAGE_ANALYSIS_JOB_TYPES and not settings.image_analysis_enabled:
        raise ValidationError("Image analysis jobs are currently disabled.")

    job_service = JobService(session)
    job_in = JobCreate(
        type=normalized_job_type,
        payload=payload,
        max_retries=max_retries,
        queue_name=queue_name,
        dedupe_key=dedupe_key,
    )
    return await job_service.create_job(job_in, reprocessed_from_job_id=reprocessed_from_job_id)
