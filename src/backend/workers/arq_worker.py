"""ARQ worker entrypoint."""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import UTC, datetime
from uuid import UUID

from arq.connections import RedisSettings

from backend.core.config import get_settings
from backend.db.session import async_session_maker
from backend.services.job_queue import resolve_queue_name
from backend.services.jobs import JobCancelledError, JobService
from backend.workers.dispatcher import get_handler
from backend.workers.handlers import ai as _ai_handler  # noqa: F401
from backend.workers.handlers import books as _books_handler  # noqa: F401
from backend.workers.handlers import comics as _comics_handler  # noqa: F401
from backend.workers.handlers import dedupe as _dedupe_handler  # noqa: F401
from backend.workers.handlers import images as _images_handler  # noqa: F401
from backend.workers.handlers import metadata as _metadata_handler  # noqa: F401
from backend.workers.handlers import move as _move_handler  # noqa: F401
from backend.workers.handlers import rules as _rules_handler  # noqa: F401
from backend.workers.handlers import sync as _sync_handler  # noqa: F401
from backend.workers.handlers import upload as _upload_handler  # noqa: F401

# Ensure worker has visible INFO logs even when launched standalone.
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

logger = logging.getLogger(__name__)

async def _fail_job_with_fresh_session(job_id: UUID, error: str) -> None:
    """Best-effort failure status update using a fresh DB session."""
    async with async_session_maker() as recovery_session:
        recovery_service = JobService(recovery_session)
        await recovery_service.fail_job(job_id, error)


async def process_job(ctx, job_id: str) -> None:
    """Execute a single job id from Redis queue."""
    settings = get_settings()
    timeout_seconds = settings.worker_job_timeout_seconds

    async with async_session_maker() as session:
        job_service = JobService(session)

        try:
            job_uuid = UUID(str(job_id))
        except ValueError:
            logger.error("Received invalid job id from queue: %s", job_id)
            return

        job = await job_service.start_job(job_uuid)
        if job is None:
            logger.info("Worker received unknown job id=%s", job_id)
            return
        job_id_value = getattr(job, "id", job_uuid)
        job_type = getattr(job, "type", "unknown")
        if job.status in {"COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED"}:
            logger.info("Skipping finalized job id=%s status=%s", job_id_value, job.status)
            return

        handler = get_handler(job_type)
        if not handler:
            await job_service.fail_job(job_id_value, f"No handler registered for type: {job_type}")
            logger.error("No handler registered for job id=%s type=%s", job_id_value, job_type)
            return

        try:
            started = datetime.now(UTC)
            logger.info("Starting job id=%s type=%s retry=%s", job_id_value, job_type, getattr(job, "retry_count", 0))
            raw_payload = job.payload
            if isinstance(raw_payload, str):
                try:
                    raw_payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    raw_payload = {}
            if not isinstance(raw_payload, dict):
                raw_payload = {}
            payload = dict(raw_payload)
            payload["_job_id"] = str(job_id_value)

            if await job_service.is_cancel_requested(job_id_value):
                await job_service.cancel_running_job(job_id_value, "Cancelled before execution started")
                logger.info("Cancelled job before execution id=%s", job_id_value)
                return

            result = await handler(payload, session)

            if await job_service.is_cancel_requested(job_id_value):
                await job_service.cancel_running_job(job_id_value, "Cancelled during execution")
                logger.info("Cancelled job during execution id=%s", job_id_value)
                return

            elapsed = (datetime.now(UTC) - started).total_seconds()
            if isinstance(result, dict):
                metrics = dict(result.get("metrics") or {})
                metrics["duration_seconds"] = round(elapsed, 3)
                result["metrics"] = metrics

            await job_service.complete_job(job_id_value, result)
            logger.info("Completed job id=%s type=%s elapsed=%.3fs", job_id_value, job_type, elapsed)
        except JobCancelledError:
            try:
                await session.rollback()
            except Exception:
                pass
            await job_service.cancel_running_job(job_id_value, "Cancelled during execution")
            logger.info("Job cancellation requested id=%s", job_id_value)
        except asyncio.CancelledError:
            # ARQ cancels the running coroutine when job timeout is reached.
            error_msg = f"Job timed out or was externally cancelled (worker timeout={timeout_seconds}s)"
            logger.error("Job %s cancelled by runtime: %s", job_id_value, error_msg)
            try:
                await session.rollback()
            except Exception:
                pass
            try:
                # Shield so we can persist status despite cancellation context.
                await asyncio.shield(_fail_job_with_fresh_session(job_id_value, error_msg))
            except Exception:
                logger.exception("Failed to persist cancelled/timeout status for job %s", job_id_value)
            raise
        except Exception as exc:
            error_msg = str(exc)
            stack_trace = traceback.format_exc()
            logger.error("Job %s failed: %s", job_id_value, error_msg)
            try:
                await session.rollback()
            except Exception:
                pass
            full_error = f"{error_msg}\n{stack_trace}"
            try:
                await job_service.fail_job(job_id_value, full_error)
            except Exception:
                logger.exception("Primary fail_job update failed for job %s. Retrying with fresh session.", job_id_value)
                try:
                    await _fail_job_with_fresh_session(job_id_value, full_error)
                except Exception:
                    logger.exception("Fallback fail_job update also failed for job %s", job_id_value)


class WorkerSettings:
    """ARQ worker config."""

    _settings = get_settings()
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    queue_name = resolve_queue_name(_settings.worker_queue_name, settings=_settings)
    max_jobs = _settings.worker_concurrency
    job_timeout = _settings.worker_job_timeout_seconds
    functions = [process_job]
