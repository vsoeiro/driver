"""Job service for managing background jobs."""

import asyncio
import inspect
import json
import logging
import math
from datetime import datetime, UTC, timedelta
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging_utils import log_event
from backend.core.config import get_settings
from backend.db.models import Job, JobAttempt
from backend.services.job_queue import JobQueue, get_job_queue
from backend.schemas.jobs import JobCreate

logger = logging.getLogger(__name__)
FINALIZED_STATUSES = {"COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED"}
QUEUE_PENDING_STATUSES = {"PENDING", "RETRY_SCHEDULED"}


class JobCancelledError(Exception):
    """Raised when a running job is cancelled by user request."""


class JobService:
    """Service to manage background jobs."""

    def __init__(self, session: AsyncSession, queue: JobQueue | None = None):
        """Initialize the job service.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        """
        self.session = session
        self.queue = queue

    async def recover_stale_running_jobs(self) -> int:
        """Mark stale RUNNING jobs as CANCELLED.

        A job is considered stale when it remains RUNNING longer than
        worker timeout + grace period, which typically indicates worker crash
        or lost cancellation callback.
        """
        settings = get_settings()
        grace_seconds = 120
        stale_after_seconds = max(60, int(settings.worker_job_timeout_seconds) + grace_seconds)
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=stale_after_seconds)
        stale_reason = (
            f"Auto-cancelled by backend stale-job recovery after {stale_after_seconds}s "
            f"without completion."
        )

        stmt = select(Job).where(
            Job.status == "RUNNING",
            Job.started_at.is_not(None),
            Job.started_at < cutoff,
        )
        result = await self.session.execute(stmt)
        stale_jobs = result.scalars().all()
        if not stale_jobs:
            return 0

        stale_job_ids = [job.id for job in stale_jobs]
        for job in stale_jobs:
            current_result = self._coerce_json_dict(job.result, default_empty=True) or {}
            job.status = "CANCELLED"
            job.completed_at = now
            job.last_error = stale_reason
            job.result = {
                **current_result,
                "cancelled": True,
                "message": stale_reason,
                "stale_recovery": True,
            }
            self.session.add(job)

        attempts_stmt = select(JobAttempt).where(
            JobAttempt.job_id.in_(stale_job_ids),
            JobAttempt.completed_at.is_(None),
        )
        attempts_result = await self.session.execute(attempts_stmt)
        open_attempts = attempts_result.scalars().all()
        for attempt in open_attempts:
            started_at = attempt.started_at if isinstance(attempt.started_at, datetime) else now
            attempt.status = "CANCELLED"
            attempt.error = stale_reason
            attempt.completed_at = now
            attempt.duration_seconds = int(max(0, (now - started_at).total_seconds()))
            self.session.add(attempt)

        await self.session.commit()
        log_event(
            logger,
            "jobs_stale_recovered",
            level=logging.WARNING,
            recovered_count=len(stale_job_ids),
            stale_after_seconds=stale_after_seconds,
        )
        return len(stale_job_ids)

    async def _create_attempt(self, job_id: UUID, *, triggered_by: str = "worker") -> None:
        max_attempt_stmt = select(func.max(JobAttempt.attempt_number)).where(JobAttempt.job_id == job_id)
        max_attempt = await self.session.scalar(max_attempt_stmt)
        attempt = JobAttempt(
            job_id=job_id,
            attempt_number=(max_attempt or 0) + 1,
            status="RUNNING",
            triggered_by=triggered_by,
        )
        self.session.add(attempt)

    async def _finalize_latest_attempt(self, job_id: UUID, *, status: str, error: str | None = None) -> None:
        stmt = (
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .where(JobAttempt.completed_at.is_(None))
            .order_by(desc(JobAttempt.attempt_number))
            .limit(1)
        )
        attempt_result = (await self.session.execute(stmt)).scalar_one_or_none()
        attempt = await attempt_result if inspect.isawaitable(attempt_result) else attempt_result
        if attempt is None:
            return
        now = datetime.now(UTC)
        started_at = attempt.started_at if isinstance(attempt.started_at, datetime) else now
        attempt.status = status
        attempt.error = error
        attempt.completed_at = now
        attempt.duration_seconds = int(max(0, (now - started_at).total_seconds()))
        self.session.add(attempt)

    @staticmethod
    def _coerce_json_dict(value: Any, *, default_empty: bool = True) -> dict | None:
        """Coerce persisted JSON-like values to a Python dict.

        Handles legacy rows where JSON columns were stored as text.
        """
        if value is None:
            return {} if default_empty else None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {} if default_empty else None
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else ({} if default_empty else None)
            except json.JSONDecodeError:
                return {} if default_empty else None
        return {} if default_empty else None

    def _normalize_job_json_fields(self, job: Job) -> Job:
        """Normalize potentially string-encoded JSON fields in-place."""
        job.payload = self._coerce_json_dict(job.payload, default_empty=True)
        job.result = self._coerce_json_dict(job.result, default_empty=False)
        job.metrics = self._coerce_json_dict(job.metrics, default_empty=False)
        return job

    async def _build_avg_duration_by_type(self) -> tuple[dict[str, float], float]:
        stmt = (
            select(Job.type, Job.started_at, Job.completed_at)
            .where(
                Job.status == "COMPLETED",
                Job.started_at.is_not(None),
                Job.completed_at.is_not(None),
            )
            .order_by(Job.completed_at.desc())
            .limit(500)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        max_per_type = 10
        max_global = 10
        durations_by_type: dict[str, list[float]] = {}
        all_durations: list[float] = []
        for job_type, started_at, completed_at in rows:
            if not started_at or not completed_at:
                continue
            duration = max(1.0, (completed_at - started_at).total_seconds())
            if len(all_durations) < max_global:
                all_durations.append(duration)
            bucket = durations_by_type.setdefault(str(job_type), [])
            if len(bucket) < max_per_type:
                bucket.append(duration)

        avg_by_type = {
            job_type: (sum(values) / len(values))
            for job_type, values in durations_by_type.items()
            if values
        }
        if all_durations:
            global_avg = sum(all_durations) / len(all_durations)
        else:
            global_avg = 60.0
        return avg_by_type, max(1.0, global_avg)

    async def _build_pending_job_estimates(
        self,
        *,
        target_job_ids: set[UUID] | None = None,
    ) -> dict[UUID, dict[str, Any]]:
        settings = get_settings()
        worker_slots = max(1, int(settings.worker_concurrency))
        now = datetime.now(UTC)
        avg_by_type, global_avg = await self._build_avg_duration_by_type()
        pending_targets = set(target_job_ids or set())

        running_stmt = (
            select(Job.type, Job.started_at, Job.created_at)
            .where(Job.status == "RUNNING")
            .order_by(Job.started_at.asc().nullslast(), Job.created_at.asc())
        )
        running_rows = (await self.session.execute(running_stmt)).all()
        slot_available_at = [0.0 for _ in range(worker_slots)]
        for job_type, started_at, _created_at in running_rows:
            avg_duration = avg_by_type.get(str(job_type), global_avg)
            elapsed = max(
                0.0,
                (now - started_at).total_seconds() if started_at else 0.0,
            )
            remaining = max(1.0, avg_duration - elapsed)
            slot_index = min(range(worker_slots), key=lambda i: slot_available_at[i])
            slot_available_at[slot_index] += remaining

        queued_stmt = (
            select(Job.id, Job.type, Job.status, Job.next_retry_at, Job.created_at)
            .where(Job.status.in_(tuple(QUEUE_PENDING_STATUSES)))
            .order_by(Job.created_at.asc())
        )
        queued_rows = (await self.session.execute(queued_stmt)).all()

        estimates: dict[UUID, dict[str, Any]] = {}
        queue_position = 0
        for row_id, row_type, row_status, row_next_retry_at, row_created_at in queued_rows:
            queue_position += 1
            avg_duration = avg_by_type.get(str(row_type), global_avg)
            ready_at = row_next_retry_at if row_status == "RETRY_SCHEDULED" and row_next_retry_at else row_created_at
            ready_delay = max(0.0, (ready_at - now).total_seconds()) if ready_at else 0.0
            slot_index = min(range(worker_slots), key=lambda i: slot_available_at[i])
            estimated_wait = max(slot_available_at[slot_index], ready_delay)
            slot_available_at[slot_index] = estimated_wait + avg_duration
            estimates[row_id] = {
                "queue_position": queue_position,
                "estimated_wait_seconds": int(round(estimated_wait)),
                "estimated_duration_seconds": int(round(avg_duration)),
                "estimated_start_at": now + timedelta(seconds=int(round(estimated_wait))),
            }
            if pending_targets:
                pending_targets.discard(row_id)
                if not pending_targets:
                    break
        return estimates

    async def create_job(self, job_in: JobCreate, *, reprocessed_from_job_id: UUID | None = None) -> Job:
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
            reprocessed_from_job_id=reprocessed_from_job_id,
            progress_current=0,
            progress_total=None,
            progress_percent=0,
            metrics={},
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        queue = self.queue or get_job_queue()
        try:
            await queue.enqueue_job(str(job.id))
        except Exception as exc:
            logger.error("Failed to enqueue job %s: %s", job.id, exc, exc_info=True)
            await self.fail_job(job.id, f"Failed to enqueue job: {exc}")
            raise
        log_event(logger, "job_created", job_id=str(job.id), job_type=job.type, max_retries=max_retries)
        return job

    async def start_job(self, job_id: UUID) -> Job | None:
        """Claim a job for execution and mark as RUNNING."""
        await self.recover_stale_running_jobs()
        job = await self.session.get(Job, job_id)
        if not job:
            return None
        if job.status in {"COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED"}:
            return self._normalize_job_json_fields(job)
        if job.status == "RUNNING":
            return self._normalize_job_json_fields(job)

        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        job.last_error = None
        job.next_retry_at = None
        self.session.add(job)
        await self._create_attempt(job.id, triggered_by="worker")
        await self.session.commit()
        await self.session.refresh(job)
        log_event(logger, "job_started", job_id=str(job.id), job_type=job.type, retry_count=job.retry_count)
        return self._normalize_job_json_fields(job)

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
        await self._finalize_latest_attempt(job_id, status="COMPLETED")
        await self.session.commit()
        log_event(logger, "job_completed", job_id=str(job_id))
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
        current_result = self._coerce_json_dict(job.result, default_empty=True) or {}
        job.result = {
            **current_result,
            "cancelled": True,
            "message": "Cancelled by user",
        }

        self.session.add(job)
        await self._finalize_latest_attempt(job.id, status="CANCELLED", error="Cancelled by user")
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
        await self._finalize_latest_attempt(job_id, status="CANCELLED", error=message)
        await self.session.commit()
        return self._normalize_job_json_fields(job)

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
            log_event(
                logger,
                "job_retry_scheduled",
                level=logging.WARNING,
                job_id=str(job_id),
                retry_count=next_retry_count,
                max_retries=job.max_retries,
                retry_in_seconds=delay_seconds,
            )
            await self._finalize_latest_attempt(job.id, status="RETRY_SCHEDULED", error=error)
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
            log_event(
                logger,
                "job_failed_permanently",
                level=logging.ERROR,
                job_id=str(job_id),
                dead_lettered=dead_lettered,
                error=error,
            )
            await self._finalize_latest_attempt(job.id, status=job.status, error=error)

        self.session.add(job)
        await self.session.commit()
        if job.status == "RETRY_SCHEDULED":
            queue = self.queue or get_job_queue()
            delay = max(0, int((job.next_retry_at - now).total_seconds())) if job.next_retry_at else 0
            try:
                await queue.enqueue_job(str(job.id), defer_seconds=delay)
            except Exception as exc:
                logger.error(
                    "Failed to enqueue retry for job %s: %s",
                    job.id,
                    exc,
                    exc_info=True,
                )
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

    async def get_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
        statuses: Sequence[str] | None = None,
        job_types: Sequence[str] | None = None,
        created_after: datetime | None = None,
        include_estimates: bool = True,
    ) -> Sequence[Job]:
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
        normalized_statuses = [status.strip().upper() for status in (statuses or []) if status and status.strip()]
        normalized_job_types = [job_type.strip().lower() for job_type in (job_types or []) if job_type and job_type.strip()]
        normalized_created_after = created_after
        if normalized_created_after and normalized_created_after.tzinfo is None:
            normalized_created_after = normalized_created_after.replace(tzinfo=UTC)
        if normalized_statuses:
            stmt = stmt.where(Job.status.in_(normalized_statuses))
        if normalized_job_types:
            stmt = stmt.where(Job.type.in_(normalized_job_types))
        if normalized_created_after is not None:
            stmt = stmt.where(Job.created_at >= normalized_created_after)
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                result = await self.session.execute(stmt)
                jobs = result.scalars().all()
                pending_job_ids = {
                    job.id
                    for job in jobs
                    if job.status in QUEUE_PENDING_STATUSES
                }
                estimates: dict[UUID, dict[str, Any]] = {}
                if include_estimates and pending_job_ids:
                    estimates = await self._build_pending_job_estimates(
                        target_job_ids=pending_job_ids,
                    )
                for job in jobs:
                    self._normalize_job_json_fields(job)
                    estimate = estimates.get(job.id) if include_estimates else None
                    if estimate and job.status in QUEUE_PENDING_STATUSES:
                        job.queue_position = estimate["queue_position"]
                        job.estimated_wait_seconds = estimate["estimated_wait_seconds"]
                        job.estimated_duration_seconds = estimate["estimated_duration_seconds"]
                        job.estimated_start_at = estimate["estimated_start_at"]
                    else:
                        job.queue_position = None
                        job.estimated_wait_seconds = None
                        job.estimated_duration_seconds = None
                        job.estimated_start_at = None
                return jobs
            except OperationalError as exc:
                if "database is locked" not in str(exc).lower() or attempt == max_attempts:
                    raise
                await asyncio.sleep(0.15 * attempt)

        return []

    async def get_job_attempts(self, job_id: UUID, limit: int = 20) -> Sequence[JobAttempt]:
        """Return attempt history for one job ordered by latest attempt first."""
        job_exists = await self.session.scalar(select(func.count(Job.id)).where(Job.id == job_id))
        if not job_exists:
            raise ValueError(f"Job {job_id} not found")
        stmt = (
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number.desc())
            .limit(max(1, limit))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def reprocess_job(self, job_id: UUID) -> Job:
        """Create a new PENDING job cloned from a finalized job."""
        source_job = await self.session.get(Job, job_id)
        if source_job is None:
            raise ValueError(f"Job {job_id} not found")

        finalized_statuses = {"COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED"}
        if source_job.status not in finalized_statuses:
            raise ValueError("Only finalized jobs can be reprocessed")

        payload = self._coerce_json_dict(source_job.payload, default_empty=True) or {}
        cloned = JobCreate(
            type=source_job.type,
            payload=payload,
            max_retries=source_job.max_retries or 0,
        )
        new_job = await self.create_job(cloned, reprocessed_from_job_id=source_job.id)
        log_event(
            logger,
            "job_reprocessed",
            job_id=str(new_job.id),
            source_job_id=str(source_job.id),
            source_status=source_job.status,
        )
        return new_job

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
