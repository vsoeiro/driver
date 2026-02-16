"""Background worker runner."""

import asyncio
import logging
import traceback
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from backend.services.jobs import JobService
from backend.workers.dispatcher import get_handler

logger = logging.getLogger(__name__)


class BackgroundWorker:
    """Background worker that polls for jobs and executes them."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_interval: float = 5.0,
    ):
        """Initialize the background worker.

        Parameters
        ----------
        session_factory : async_sessionmaker[AsyncSession]
            Factory to create database sessions.
        poll_interval : float, optional
            Time in seconds to wait when no jobs are found, by default 5.0.
        """
        self.session_factory = session_factory
        self.poll_interval = poll_interval
        self.running = False

    async def start(self):
        """Start the worker loop."""
        self.running = True
        logger.info("Background worker started")
        while self.running:
            try:
                await self.process_next_job()
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    def stop(self):
        """Stop the worker loop."""
        self.running = False
        logger.info("Background worker stopping...")

    async def process_next_job(self):
        """Process a single job."""
        async with self.session_factory() as session:
            job_service = JobService(session)
            job = await job_service.get_next_job()

            if not job:
                # No jobs found, sleep
                await asyncio.sleep(self.poll_interval)
                return

            handler = get_handler(job.type)
            if not handler:
                logger.error(f"No handler found for job type: {job.type}")
                await job_service.fail_job(job.id, f"No handler registered for type: {job.type}")
                return

            try:
                logger.info(f"Executing job {job.id} ({job.type})")

                started = datetime.now(UTC)
                payload = dict(job.payload or {})
                payload["_job_id"] = str(job.id)

                # Execute the handler with payload/session.
                result = await handler(payload, session)

                elapsed = (datetime.now(UTC) - started).total_seconds()
                if isinstance(result, dict):
                    metrics = dict(result.get("metrics") or {})
                    metrics["duration_seconds"] = round(elapsed, 3)
                    result["metrics"] = metrics

                await job_service.complete_job(job.id, result)
            except Exception as e:
                error_msg = str(e)
                stack_trace = traceback.format_exc()
                logger.error(f"Job {job.id} failed: {error_msg}")
                try:
                    await session.rollback()
                except Exception:
                    pass
                await job_service.fail_job(job.id, f"{error_msg}\n{stack_trace}")
