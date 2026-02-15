"""Daily scheduler to enqueue sync jobs for all active accounts."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import LinkedAccount
from backend.schemas.jobs import JobCreate
from backend.services.jobs import JobService

logger = logging.getLogger(__name__)


class DailySyncScheduler:
    """Enqueue one sync job per active account every day at a fixed time."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        hour: int = 0,
        minute: int = 0,
    ) -> None:
        self.session_factory = session_factory
        self.hour = hour
        self.minute = minute
        self._running = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Run the scheduling loop until stopped."""
        self._running = True
        logger.info(
            "Daily sync scheduler started. Next runs at %02d:%02d (server local time).",
            self.hour,
            self.minute,
        )

        while self._running:
            now = datetime.now().astimezone()
            sleep_seconds = self._seconds_until_next_run(now, self.hour, self.minute)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_seconds)
                break
            except asyncio.TimeoutError:
                pass

            if not self._running:
                break

            await self.enqueue_sync_jobs_for_all_accounts()

        logger.info("Daily sync scheduler stopped.")

    def stop(self) -> None:
        """Stop the scheduling loop."""
        self._running = False
        self._stop_event.set()

    async def enqueue_sync_jobs_for_all_accounts(self) -> int:
        """Create one `sync_items` job for each active linked account."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(LinkedAccount.id).where(LinkedAccount.is_active.is_(True))
            )
            account_ids = result.scalars().all()

            if not account_ids:
                logger.info("Daily sync scheduler found no active accounts.")
                return 0

            job_service = JobService(session)
            for account_id in account_ids:
                await job_service.create_job(
                    JobCreate(
                        type="sync_items",
                        payload={"account_id": str(account_id)},
                    )
                )

            logger.info(
                "Daily sync scheduler enqueued %d sync jobs.",
                len(account_ids),
            )
            return len(account_ids)

    @staticmethod
    def _seconds_until_next_run(now: datetime, hour: int, minute: int) -> float:
        """Compute seconds until the next run at `hour:minute`."""
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run + timedelta(days=1)
        return (next_run - now).total_seconds()
