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
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging_utils import log_event
from backend.core.config import get_settings
from backend.db.models import Job, JobAttempt
from backend.domain.errors import NotFoundError, ValidationError
from backend.domain.jobs.policies import (
    resolve_job_dedupe_key,
    resolve_job_max_retries,
    resolve_job_queue_alias,
)
from backend.domain.jobs.types import JobStatus, normalize_job_type
from backend.services.job_queue import JobQueue, get_job_queue, resolve_queue_name
from backend.schemas.jobs import JobCreate

logger = logging.getLogger(__name__)
FINALIZED_STATUSES = {
    JobStatus.COMPLETED.value,
    JobStatus.FAILED.value,
    JobStatus.DEAD_LETTER.value,
    JobStatus.CANCELLED.value,
}
QUEUE_PENDING_STATUSES = {JobStatus.PENDING.value, JobStatus.RETRY_SCHEDULED.value}
ACTIVE_DEDUPE_STATUSES = {
    JobStatus.PENDING.value,
    JobStatus.RUNNING.value,
    JobStatus.RETRY_SCHEDULED.value,
}
QUEUE_DISPATCHABLE_STATUSES = {
    JobStatus.PENDING.value,
    JobStatus.RETRY_SCHEDULED.value,
}


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
        self.settings = get_settings()

    def _resolve_job_queue_name(self, job_type: str, requested_queue_name: str | None) -> str:
        queue_alias_or_name = resolve_job_queue_alias(job_type, self.settings, requested_queue_name)
        return resolve_queue_name(queue_alias_or_name, settings=self.settings)

    def _resolve_job_max_retries(self, job_type: str, requested_max_retries: int | None) -> int:
        return resolve_job_max_retries(job_type, self.settings, requested_max_retries)

    def _resolve_job_dedupe_key(
        self,
        job_type: str,
        payload: dict[str, Any],
        requested_dedupe_key: str | None,
    ) -> str | None:
        return resolve_job_dedupe_key(
            job_type=job_type,
            payload=payload,
            requested_dedupe_key=requested_dedupe_key,
        )

    async def _find_active_duplicate_job(self, dedupe_key: str) -> Job | None:
        stmt = (
            select(Job)
            .where(
                Job.dedupe_key == dedupe_key,
                Job.status.in_(tuple(ACTIVE_DEDUPE_STATUSES)),
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        duplicate = (await self.session.execute(stmt)).scalar_one_or_none()
        if duplicate is None:
            return None
        return self._normalize_job_json_fields(duplicate)

    async def recover_stale_running_jobs(self) -> int:
        """Mark stale RUNNING jobs as CANCELLED.

        A job is considered stale when it remains RUNNING longer than
        worker timeout + grace period, which typically indicates worker crash
        or lost cancellation callback.
        """
        settings = self.settings
        grace_seconds = 120
        stale_after_seconds = max(60, int(settings.worker_job_timeout_seconds) + grace_seconds)
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=stale_after_seconds)
        stale_reason = (
            f"Auto-cancelled by backend stale-job recovery after {stale_after_seconds}s "
            f"without completion."
        )

        stmt = select(Job).where(
            Job.status == JobStatus.RUNNING.value,
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
            job.status = JobStatus.CANCELLED.value
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
            status=JobStatus.RUNNING.value,
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

    async def _persist_job_dispatch_state(self, job: Job) -> None:
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)

    async def dispatch_job(self, job: Job, *, defer_seconds: int = 0) -> Job:
        """Enqueue a persisted job and track dispatch outcome in the database."""
        if job.status not in QUEUE_DISPATCHABLE_STATUSES:
            return self._normalize_job_json_fields(job)

        queue_name = self._resolve_job_queue_name(str(job.type), getattr(job, "queue_name", None))
        queue = self.queue or get_job_queue()
        job.queue_name = queue_name
        job.queue_dispatch_attempts = int(getattr(job, "queue_dispatch_attempts", 0) or 0) + 1

        try:
            await queue.enqueue_job(
                str(job.id),
                queue_name=queue_name,
                defer_seconds=max(0, int(defer_seconds)),
            )
        except Exception as exc:
            logger.error("Failed to enqueue job %s: %s", job.id, exc, exc_info=True)
            job.queue_enqueued_at = None
            job.queue_last_error = str(exc)
            await self._persist_job_dispatch_state(job)
            return self._normalize_job_json_fields(job)

        job.queue_enqueued_at = datetime.now(UTC)
        job.queue_last_error = None
        await self._persist_job_dispatch_state(job)
        return self._normalize_job_json_fields(job)

    async def reconcile_pending_dispatches(self, *, limit: int = 100) -> int:
        """Best-effort re-enqueue for persisted jobs still awaiting Redis dispatch."""
        now = datetime.now(UTC)
        stmt = (
            select(Job)
            .where(
                Job.status.in_(tuple(QUEUE_DISPATCHABLE_STATUSES)),
                Job.queue_enqueued_at.is_(None),
            )
            .order_by(Job.created_at.asc())
            .limit(max(1, limit))
        )
        result = await self.session.execute(stmt)
        jobs = result.scalars().all()
        reconciled = 0
        for job in jobs:
            delay_seconds = 0
            if job.status == JobStatus.RETRY_SCHEDULED.value and job.next_retry_at is not None:
                delay_seconds = max(0, int((job.next_retry_at - now).total_seconds()))
            dispatched = await self.dispatch_job(job, defer_seconds=delay_seconds)
            if dispatched.queue_enqueued_at is not None:
                reconciled += 1
        return reconciled

    async def _build_avg_duration_by_type(self) -> tuple[dict[str, float], float]:
        stmt = (
            select(Job.type, Job.started_at, Job.completed_at)
            .where(
                Job.status == JobStatus.COMPLETED.value,
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
        settings = self.settings
        worker_slots = max(1, int(settings.worker_concurrency))
        now = datetime.now(UTC)
        avg_by_type, global_avg = await self._build_avg_duration_by_type()
        pending_targets = set(target_job_ids or set())
        default_queue_name = resolve_queue_name(None, settings=self.settings)

        running_stmt = (
            select(Job.queue_name, Job.type, Job.started_at, Job.created_at)
            .where(Job.status == "RUNNING")
            .order_by(Job.queue_name.asc().nullslast(), Job.started_at.asc().nullslast(), Job.created_at.asc())
        )
        running_rows = (await self.session.execute(running_stmt)).all()
        slot_available_by_queue: dict[str, list[float]] = {}
        for queue_name, job_type, started_at, _created_at in running_rows:
            avg_duration = avg_by_type.get(str(job_type), global_avg)
            elapsed = max(
                0.0,
                (now - started_at).total_seconds() if started_at else 0.0,
            )
            remaining = max(1.0, avg_duration - elapsed)
            normalized_queue_name = queue_name or default_queue_name
            slot_available_at = slot_available_by_queue.setdefault(
                normalized_queue_name,
                [0.0 for _ in range(worker_slots)],
            )
            slot_index = min(range(worker_slots), key=lambda i: slot_available_at[i])
            slot_available_at[slot_index] += remaining

        queued_stmt = (
            select(Job.id, Job.queue_name, Job.type, Job.status, Job.next_retry_at, Job.created_at)
            .where(Job.status.in_(tuple(QUEUE_PENDING_STATUSES)))
            .order_by(Job.queue_name.asc().nullslast(), Job.created_at.asc())
        )
        queued_rows = (await self.session.execute(queued_stmt)).all()

        estimates: dict[UUID, dict[str, Any]] = {}
        queue_position_by_queue: dict[str, int] = {}
        for row_id, row_queue_name, row_type, row_status, row_next_retry_at, row_created_at in queued_rows:
            normalized_queue_name = row_queue_name or default_queue_name
            queue_position_by_queue[normalized_queue_name] = queue_position_by_queue.get(normalized_queue_name, 0) + 1
            queue_position = queue_position_by_queue[normalized_queue_name]
            avg_duration = avg_by_type.get(str(row_type), global_avg)
            ready_at = row_next_retry_at if row_status == "RETRY_SCHEDULED" and row_next_retry_at else row_created_at
            ready_delay = max(0.0, (ready_at - now).total_seconds()) if ready_at else 0.0
            slot_available_at = slot_available_by_queue.setdefault(
                normalized_queue_name,
                [0.0 for _ in range(worker_slots)],
            )
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
        normalized_type = normalize_job_type(job_in.type)
        payload_json = job_in.payload if isinstance(job_in.payload, dict) else {}

        max_retries = self._resolve_job_max_retries(normalized_type, job_in.max_retries)
        queue_name = self._resolve_job_queue_name(normalized_type, job_in.queue_name)
        dedupe_key = self._resolve_job_dedupe_key(normalized_type, payload_json, job_in.dedupe_key)

        if dedupe_key:
            duplicate = await self._find_active_duplicate_job(dedupe_key)
            if duplicate is not None:
                log_event(
                    logger,
                    "job_duplicate_suppressed",
                    level=logging.INFO,
                    dedupe_key=dedupe_key,
                    duplicate_job_id=str(duplicate.id),
                    job_type=normalized_type,
                )
                return duplicate

        job = Job(
            type=normalized_type,
            payload=payload_json,
            status=JobStatus.PENDING.value,
            queue_name=queue_name,
            dedupe_key=dedupe_key,
            queue_enqueued_at=None,
            queue_dispatch_attempts=0,
            queue_last_error=None,
            max_retries=max_retries,
            reprocessed_from_job_id=reprocessed_from_job_id,
            progress_current=0,
            progress_total=None,
            progress_percent=0,
            metrics={},
        )
        self.session.add(job)

        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            if dedupe_key:
                duplicate = await self._find_active_duplicate_job(dedupe_key)
                if duplicate is not None:
                    log_event(
                        logger,
                        "job_duplicate_suppressed",
                        level=logging.INFO,
                        dedupe_key=dedupe_key,
                        duplicate_job_id=str(duplicate.id),
                        job_type=normalized_type,
                        conflict_recovered=True,
                    )
                    return duplicate
            raise

        await self.session.refresh(job)
        job = await self.dispatch_job(job)
        log_event(
            logger,
            "job_created",
            job_id=str(job.id),
            job_type=job.type,
            queue_name=job.queue_name,
            max_retries=max_retries,
            dedupe_key=dedupe_key,
            queue_enqueued=bool(job.queue_enqueued_at),
        )
        return job

    async def start_job(self, job_id: UUID) -> Job | None:
        """Claim a job for execution and mark as RUNNING."""
        await self.recover_stale_running_jobs()
        job = await self.session.get(Job, job_id)
        if not job:
            return None
        if job.status in FINALIZED_STATUSES:
            setattr(job, "_claimed_by_worker", False)
            return self._normalize_job_json_fields(job)
        if job.status == JobStatus.RUNNING.value:
            setattr(job, "_claimed_by_worker", False)
            return self._normalize_job_json_fields(job)
        if not getattr(job, "queue_name", None):
            job.queue_name = self._resolve_job_queue_name(str(job.type), None)

        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.now(UTC)
        job.last_error = None
        job.next_retry_at = None
        job.queue_last_error = None
        self.session.add(job)
        await self._create_attempt(job.id, triggered_by="worker")
        await self.session.commit()
        await self.session.refresh(job)
        setattr(job, "_claimed_by_worker", True)
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
        await self._finalize_latest_attempt(job_id, status=JobStatus.COMPLETED.value)
        await self.session.commit()
        log_event(logger, "job_completed", job_id=str(job_id))
        return job

    async def request_cancel(self, job_id: UUID) -> Job:
        """Request cancellation for a job.

        - PENDING/RETRY_SCHEDULED/RUNNING/CANCEL_REQUESTED: cancelled immediately
        - finalized jobs: raises ValidationError
        """
        job = await self.session.get(Job, job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")
        if job.status == JobStatus.CANCELLED.value:
            logger.info("Job %s failure ignored because it was cancelled", job_id)
            return job

        if job.status in FINALIZED_STATUSES:
            raise ValidationError("Finalized jobs cannot be cancelled")

        now = datetime.now(UTC)
        job.status = JobStatus.CANCELLED.value
        job.completed_at = now
        current_result = self._coerce_json_dict(job.result, default_empty=True) or {}
        job.result = {
            **current_result,
            "cancelled": True,
            "message": "Cancelled by user",
        }

        self.session.add(job)
        await self._finalize_latest_attempt(job.id, status=JobStatus.CANCELLED.value, error="Cancelled by user")
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def is_cancel_requested(self, job_id: UUID) -> bool:
        """Check whether a running job has a cancellation request."""
        status = await self.session.scalar(select(Job.status).where(Job.id == job_id))
        return status in {"CANCEL_REQUESTED", JobStatus.CANCELLED.value}

    async def cancel_running_job(self, job_id: UUID, message: str = "Cancelled by user") -> Job:
        """Finalize a running/cancel-requested job as cancelled."""
        now = datetime.now(UTC)
        current_status = await self.session.scalar(select(Job.status).where(Job.id == job_id))
        if current_status == JobStatus.CANCELLED.value:
            existing = await self.session.get(Job, job_id)
            if existing is None:
                raise NotFoundError(f"Job {job_id} not found")
            logger.info("Job %s completion ignored because it was cancelled", job_id)
            return existing

        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(
                status=JobStatus.CANCELLED.value,
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
        await self._finalize_latest_attempt(job_id, status=JobStatus.CANCELLED.value, error=message)
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
            raise NotFoundError(f"Job {job_id} not found")

        now = datetime.now(UTC)
        next_retry_count = (job.retry_count or 0) + 1
        retry_allowed = next_retry_count <= (job.max_retries or 0)

        if retry_allowed:
            # Exponential backoff: 2, 4, 8, ... capped to 300 seconds.
            delay_seconds = min(300, int(math.pow(2, next_retry_count)))
            job.status = JobStatus.RETRY_SCHEDULED.value
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
            await self._finalize_latest_attempt(job.id, status=JobStatus.RETRY_SCHEDULED.value, error=error)
        else:
            dead_lettered = (job.max_retries or 0) > 0
            job.status = JobStatus.DEAD_LETTER.value if dead_lettered else JobStatus.FAILED.value
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
        if job.status == JobStatus.RETRY_SCHEDULED.value:
            delay = max(0, int((job.next_retry_at - now).total_seconds())) if job.next_retry_at else 0
            job.queue_enqueued_at = None
            job = await self.dispatch_job(job, defer_seconds=delay)
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
            .where(
                Job.id == job_id,
                ~Job.status.in_(("CANCEL_REQUESTED", JobStatus.CANCELLED.value)),
            )
            .values(**values)
            .returning(Job)
        )
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()
        if job is None:
            status = await self.session.scalar(select(Job.status).where(Job.id == job_id))
            if status in {"CANCEL_REQUESTED", JobStatus.CANCELLED.value}:
                raise JobCancelledError("Job cancellation was requested")
            raise NotFoundError(f"Job {job_id} not found")
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
            raise NotFoundError(f"Job {job_id} not found")
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
            raise NotFoundError(f"Job {job_id} not found")

        if source_job.status not in FINALIZED_STATUSES:
            raise ValidationError("Only finalized jobs can be reprocessed")

        payload = self._coerce_json_dict(source_job.payload, default_empty=True) or {}
        cloned = JobCreate(
            type=source_job.type,
            payload=payload,
            max_retries=source_job.max_retries or 0,
            queue_name=source_job.queue_name,
            dedupe_key=None,
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
            raise NotFoundError(f"Job {job_id} not found")

        if job.status not in FINALIZED_STATUSES:
            raise ValidationError("Only finalized jobs can be deleted")

        await self.session.delete(job)
        await self.session.commit()
