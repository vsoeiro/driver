"""Helpers for reporting background job progress from handlers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.jobs import JobService


@dataclass
class JobProgressReporter:
    """Progress reporter built from handler payload metadata."""

    session: AsyncSession
    job_id: uuid.UUID | None
    current: int = 0
    total: int | None = None
    metrics: dict = field(default_factory=dict)

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
        await self.flush()

    async def increment(self, amount: int = 1) -> None:
        self.current += amount
        await self.flush()

    async def update_metrics(self, **metrics: int | float | str | None) -> None:
        for key, value in metrics.items():
            if value is not None:
                self.metrics[key] = value
        await self.flush()

    async def flush(self) -> None:
        if not self.job_id:
            return
        bind = self.session.bind
        if bind is None:
            return
        async with AsyncSession(bind=bind, expire_on_commit=False) as progress_session:
            service = JobService(progress_session)
            await service.update_job_progress(
                self.job_id,
                current=self.current,
                total=self.total,
                metrics=self.metrics,
            )
