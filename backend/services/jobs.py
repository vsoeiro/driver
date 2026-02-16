"""Job service for managing background jobs."""

import logging
import math
from datetime import datetime, UTC, timedelta
from typing import Sequence
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Job
from backend.schemas.jobs import JobCreate

logger = logging.getLogger(__name__)


class JobCancelledError(Exception):
    """Raised when a running job is cancelled by user request."""


class JobService:
    """Service to manage background jobs."""

    def __init__(self, session: AsyncSession):
        """Initialize the job service.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        """
        self.session = session

    async def create_job(self, job_in: JobCreate) -> Job:
        """Create a new job.

        Parameters
        ----------
        job_in : JobCreate
            Job creation schema.

        Returns
        -------
        Job
            Created job instance.
        """
        payload_json = job_in.payload if job_in.payload else {}
        
        max_retries = max(0, job_in.max_retries)

        job = Job(
            type=job_in.type,
            payload=payload_json,
            status="PENDING",
            max_retries=max_retries,
            progress_current=0,
            progress_total=None,
            progress_percent=0,
            metrics={},
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        logger.info(f"Created job {job.id} of type {job.type}")
        return job

    async def get_next_job(self) -> Job | None:
        """Get the next pending job and mark it as RUNNING.
        
        This mimics a queue by selecting the oldest PENDING job.
        
        Returns
        -------
        Job | None
            The next job to process, or None if no jobs are pending.
        """
        # Select the oldest pending job
        # Note: In a high-concurrency Postgres env, we'd use WITH LOCK matching
        # But for SQLite/Simple setup, this simple transaction is okay for now
        # as long as we commit the status change quickly.
        stmt = (
            select(Job)
            .where(
                or_(
                    Job.status == "PENDING",
                    and_(
                        Job.status == "RETRY_SCHEDULED",
                        or_(Job.next_retry_at.is_(None), Job.next_retry_at <= datetime.now(UTC)),
                    ),
                )
            )
            .order_by(Job.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        
        # SQLite doesn't support skip_locked well in all versions/drivers, falling back if needed
        # But SQLAlchemy handles some of this. If it fails, we might just grab one.
        try:
            result = await self.session.execute(stmt)
            job = result.scalar_one_or_none()
        except Exception:
            # Fallback for drivers not supporting FOR UPDATE with SKIP LOCKED
            stmt = (
                select(Job)
                .where(
                    or_(
                        Job.status == "PENDING",
                        and_(
                            Job.status == "RETRY_SCHEDULED",
                            or_(Job.next_retry_at.is_(None), Job.next_retry_at <= datetime.now(UTC)),
                        ),
                    )
                )
                .order_by(Job.created_at.asc())
                .limit(1)
            )
            result = await self.session.execute(stmt)
            job = result.scalar_one_or_none()

        if job:
            job.status = "RUNNING"
            job.started_at = datetime.now(UTC)
            job.last_error = None
            job.next_retry_at = None
            await self.session.commit()
            await self.session.refresh(job)
            logger.info(f"Picked up job {job.id}")
            return job
        
        return None

    async def complete_job(self, job_id: UUID, result: dict | None = None) -> Job:
        """Mark a job as COMPLETED.

        Parameters
        ----------
        job_id : UUID
            Job ID.
        result : dict | None, optional
            Job result payload.

        Returns
        -------
        Job
            Updated job instance.
        """
        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="COMPLETED",
                result=result or {},
                progress_percent=100,
                completed_at=datetime.now(UTC),
            )
            .returning(Job)
        )
        result = await self.session.execute(stmt)
        job = result.scalar_one()
        await self.session.commit()
        logger.info(f"Job {job_id} completed successfully")
        return job

    async def request_cancel(self, job_id: UUID) -> Job:
        """Request cancellation for a job.

        - PENDING/RETRY_SCHEDULED/RUNNING/CANCEL_REQUESTED: cancelled immediately
        - finalized jobs: raises ValueError
        """
        job = await self.session.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status == "CANCELLED":
            logger.info("Job %s failure ignored because it was cancelled", job_id)
            return job

        finalized_statuses = {"COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED"}
        if job.status in finalized_statuses:
            raise ValueError("Finalized jobs cannot be cancelled")

        now = datetime.now(UTC)
        job.status = "CANCELLED"
        job.completed_at = now
        job.result = {
            **(job.result or {}),
            "cancelled": True,
            "message": "Cancelled by user",
        }

        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def is_cancel_requested(self, job_id: UUID) -> bool:
        """Check whether a running job has a cancellation request."""
        status = await self.session.scalar(select(Job.status).where(Job.id == job_id))
        return status in {"CANCEL_REQUESTED", "CANCELLED"}

    async def cancel_running_job(self, job_id: UUID, message: str = "Cancelled by user") -> Job:
        """Finalize a running/cancel-requested job as cancelled."""
        now = datetime.now(UTC)
        current_status = await self.session.scalar(select(Job.status).where(Job.id == job_id))
        if current_status == "CANCELLED":
            existing = await self.session.get(Job, job_id)
            if existing is None:
                raise ValueError(f"Job {job_id} not found")
            logger.info("Job %s completion ignored because it was cancelled", job_id)
            return existing

        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="CANCELLED",
                completed_at=now,
                result={
                    "cancelled": True,
                    "message": message,
                },
            )
            .returning(Job)
        )
        result = await self.session.execute(stmt)
        job = result.scalar_one()
        await self.session.commit()
        return job

    async def fail_job(self, job_id: UUID, error: str) -> Job:
        """Mark a job as retry scheduled or dead-letter/failed.

        Parameters
        ----------
        job_id : UUID
            Job ID.
        error : str
            Error message.

        Returns
        -------
        Job
            Updated job instance.
        """
        job = await self.session.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        now = datetime.now(UTC)
        next_retry_count = (job.retry_count or 0) + 1
        retry_allowed = next_retry_count <= (job.max_retries or 0)

        if retry_allowed:
            # Exponential backoff: 2, 4, 8, ... capped to 300 seconds.
            delay_seconds = min(300, int(math.pow(2, next_retry_count)))
            job.status = "RETRY_SCHEDULED"
            job.retry_count = next_retry_count
            job.last_error = error
            job.next_retry_at = now + timedelta(seconds=delay_seconds)
            job.result = {"error": error, "retry_in_seconds": delay_seconds}
            job.completed_at = None
            logger.warning(
                "Job %s failed (attempt %s/%s). Retrying in %ss.",
                job_id,
                next_retry_count,
                job.max_retries,
                delay_seconds,
            )
        else:
            dead_lettered = (job.max_retries or 0) > 0
            job.status = "DEAD_LETTER" if dead_lettered else "FAILED"
            job.retry_count = next_retry_count
            job.last_error = error
            job.result = {"error": error}
            job.completed_at = now
            if dead_lettered:
                job.dead_lettered_at = now
                job.dead_letter_reason = error
            logger.error(f"Job {job_id} failed permanently: {error}")

        self.session.add(job)
        await self.session.commit()
        return job

    async def update_job_progress(
        self,
        job_id: UUID,
        *,
        current: int,
        total: int | None = None,
        metrics: dict | None = None,
    ) -> Job:
        """Persist job progress and metrics."""
        if await self.is_cancel_requested(job_id):
            raise JobCancelledError("Job cancellation was requested")

        current = max(0, current)
        progress_percent = 0
        if total is not None and total > 0:
            progress_percent = min(100, max(0, int((current / total) * 100)))

        values = {
            "progress_current": current,
            "progress_total": total,
            "progress_percent": progress_percent,
        }
        if metrics is not None:
            values["metrics"] = metrics

        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(**values)
            .returning(Job)
        )
        result = await self.session.execute(stmt)
        job = result.scalar_one()
        await self.session.commit()
        return job

    async def get_jobs(self, limit: int = 50, offset: int = 0) -> Sequence[Job]:
        """Get a list of jobs ordered by creation date (newest first).

        Parameters
        ----------
        limit : int, optional
            Number of jobs to return. Defaults to 50.
        offset : int, optional
            Offset for pagination. Defaults to 0.

        Returns
        -------
        Sequence[Job]
            List of jobs.
        """
        await self.session.execute(
            update(Job)
            .where(Job.status == "CANCEL_REQUESTED")
            .values(
                status="CANCELLED",
                completed_at=datetime.now(UTC),
                result={"cancelled": True, "message": "Cancelled by user"},
            )
        )
        await self.session.commit()

        stmt = (
            select(Job)
            .order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_job(self, job_id: UUID) -> None:
        """Delete a finalized job from history."""
        job = await self.session.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        finalized_statuses = {"COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED"}
        if job.status not in finalized_statuses:
            raise ValueError("Only finalized jobs can be deleted")

        await self.session.delete(job)
        await self.session.commit()
