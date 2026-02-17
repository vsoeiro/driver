"""ARQ worker entrypoint."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime
from uuid import UUID

from arq.connections import RedisSettings

from backend.core.config import get_settings
from backend.db.session import async_session_maker
from backend.services.jobs import JobCancelledError, JobService
from backend.workers.dispatcher import get_handler
from backend.workers.handlers import comics as _comics_handler  # noqa: F401
from backend.workers.handlers import metadata as _metadata_handler  # noqa: F401
from backend.workers.handlers import move as _move_handler  # noqa: F401
from backend.workers.handlers import rules as _rules_handler  # noqa: F401
from backend.workers.handlers import sync as _sync_handler  # noqa: F401
from backend.workers.handlers import upload as _upload_handler  # noqa: F401

logger = logging.getLogger(__name__)


async def process_job(ctx, job_id: str) -> None:
    """Execute a single job id from Redis queue."""
    settings = get_settings()
    del settings  # settings already validated on import; keeps startup parity.

    async with async_session_maker() as session:
        job_service = JobService(session)

        try:
            job_uuid = UUID(str(job_id))
        except ValueError:
            logger.error("Received invalid job id from queue: %s", job_id)
            return

        job = await job_service.start_job(job_uuid)
        if job is None:
            return
        if job.status in {"COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED"}:
            return

        handler = get_handler(job.type)
        if not handler:
            await job_service.fail_job(job.id, f"No handler registered for type: {job.type}")
            return

        try:
            started = datetime.now(UTC)
            raw_payload = job.payload
            if isinstance(raw_payload, str):
                try:
                    raw_payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    raw_payload = {}
            if not isinstance(raw_payload, dict):
                raw_payload = {}
            payload = dict(raw_payload)
            payload["_job_id"] = str(job.id)

            if await job_service.is_cancel_requested(job.id):
                await job_service.cancel_running_job(job.id, "Cancelled before execution started")
                return

            result = await handler(payload, session)

            if await job_service.is_cancel_requested(job.id):
                await job_service.cancel_running_job(job.id, "Cancelled during execution")
                return

            elapsed = (datetime.now(UTC) - started).total_seconds()
            if isinstance(result, dict):
                metrics = dict(result.get("metrics") or {})
                metrics["duration_seconds"] = round(elapsed, 3)
                result["metrics"] = metrics

            await job_service.complete_job(job.id, result)
        except JobCancelledError:
            try:
                await session.rollback()
            except Exception:
                pass
            await job_service.cancel_running_job(job.id, "Cancelled during execution")
        except Exception as exc:
            error_msg = str(exc)
            stack_trace = traceback.format_exc()
            logger.error("Job %s failed: %s", job.id, error_msg)
            try:
                await session.rollback()
            except Exception:
                pass
            await job_service.fail_job(job.id, f"{error_msg}\n{stack_trace}")


class WorkerSettings:
    """ARQ worker config."""

    _settings = get_settings()
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    queue_name = _settings.redis_queue_name
    max_jobs = _settings.worker_concurrency
    functions = [process_job]
