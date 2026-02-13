"""Job service for managing background jobs."""

import json
import logging
from datetime import datetime, UTC
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Job
from backend.schemas.jobs import JobCreate

logger = logging.getLogger(__name__)


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
        
        job = Job(
            type=job_in.type,
            payload=payload_json,
            status="PENDING",
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
            .where(Job.status == "PENDING")
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
                .where(Job.status == "PENDING")
                .order_by(Job.created_at.asc())
                .limit(1)
            )
            result = await self.session.execute(stmt)
            job = result.scalar_one_or_none()

        if job:
            job.status = "RUNNING"
            job.started_at = datetime.now(UTC)
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
                completed_at=datetime.now(UTC),
            )
            .returning(Job)
        )
        result = await self.session.execute(stmt)
        job = result.scalar_one()
        await self.session.commit()
        logger.info(f"Job {job_id} completed successfully")
        return job

    async def fail_job(self, job_id: UUID, error: str) -> Job:
        """Mark a job as FAILED.

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
        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="FAILED",
                result={"error": error},
                completed_at=datetime.now(UTC),
            )
            .returning(Job)
        )
        result = await self.session.execute(stmt)
        job = result.scalar_one()
        await self.session.commit()
        logger.error(f"Job {job_id} failed: {error}")
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
        stmt = (
            select(Job)
            .order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
