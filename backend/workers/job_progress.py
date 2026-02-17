"""Helpers for reporting background job progress from handlers."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.jobs import JobService

logger = logging.getLogger(__name__)


@dataclass
class JobProgressReporter:
    """Progress reporter built from handler payload metadata."""

    session: AsyncSession
    job_id: uuid.UUID | None
    current: int = 0
    total: int | None = None
    metrics: dict = field(default_factory=dict)
    flush_every_items: int = 25
    _last_flushed_current: int = 0

    @classmethod
    def from_payload(cls, session: AsyncSession, payload: dict) -> "JobProgressReporter":
        raw_job_id = payload.get("_job_id")
        job_id = None
        if raw_job_id:
            try:
                job_id = uuid.UUID(str(raw_job_id))
            except ValueError:
                job_id = None
        return cls(session=session, job_id=job_id)

    async def set_total(self, total: int | None) -> None:
        self.total = total
        await self.flush(force=True)

    async def increment(self, amount: int = 1) -> None:
        self.current += amount
        if self.current - self._last_flushed_current >= self.flush_every_items:
            await self.flush()

    async def update_metrics(self, **metrics: int | float | str | None) -> None:
        for key, value in metrics.items():
            if value is not None:
                self.metrics[key] = value
        await self.flush(force=True)

    async def flush(self, *, force: bool = False) -> None:
        if not self.job_id:
            return
        bind = self.session.bind
        if bind is None:
            return
        if not force and self.current == self._last_flushed_current:
            return
        try:
            async with AsyncSession(bind=bind, expire_on_commit=False) as progress_session:
                service = JobService(progress_session)
                await service.update_job_progress(
                    self.job_id,
                    current=self.current,
                    total=self.total,
                    metrics=self.metrics,
                )
                self._last_flushed_current = self.current
        except OperationalError as exc:
            # SQLite can lock during long-running writer transactions.
            # Progress is best-effort; we should not fail the job on this.
            if "database is locked" in str(exc).lower():
                logger.warning("Skipping progress update for job %s due to sqlite lock", self.job_id)
                return
            raise
