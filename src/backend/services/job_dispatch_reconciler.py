"""Periodic reconciliation for persisted jobs that were not dispatched to Redis."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.services.jobs import JobService

logger = logging.getLogger(__name__)


class JobDispatchReconciler:
    """Background loop that retries dispatch for persisted pending jobs."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        interval_seconds: int = 15,
        batch_size: int = 100,
    ) -> None:
        self.session_factory = session_factory
        self.interval_seconds = max(5, int(interval_seconds))
        self.batch_size = max(1, int(batch_size))
        self._running = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._running = True
        logger.info(
            "Job dispatch reconciler started interval=%ss batch_size=%s",
            self.interval_seconds,
            self.batch_size,
        )
        while self._running:
            try:
                async with self.session_factory() as session:
                    reconciled = await JobService(session).reconcile_pending_dispatches(limit=self.batch_size)
                if reconciled:
                    logger.info("Job dispatch reconciler re-enqueued %s jobs", reconciled)
            except Exception:
                logger.exception("Job dispatch reconciler iteration failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
                break
            except asyncio.TimeoutError:
                continue

        logger.info("Job dispatch reconciler stopped")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
