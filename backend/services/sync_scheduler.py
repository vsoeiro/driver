"""Daily scheduler to enqueue sync jobs for all active accounts."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.config import get_settings
from backend.services.app_settings import AppSettingsService, RuntimeSettings
from backend.services.cron_utils import next_run_datetime
from backend.db.models import LinkedAccount
from backend.schemas.jobs import JobCreate
from backend.services.jobs import JobService

logger = logging.getLogger(__name__)


class DailySyncScheduler:
    """Enqueue one sync job per active account based on persisted cron settings."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory
        self._running = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Run the scheduling loop until stopped."""
        self._running = True
        logger.info("Daily sync scheduler started.")
        active_signature: tuple[bool, str] | None = None
        next_run: datetime | None = None

        while self._running:
            runtime_settings = await self._get_runtime_settings()
            signature = (
                runtime_settings.enable_daily_sync_scheduler,
                runtime_settings.daily_sync_cron,
            )
            now = datetime.now().astimezone()

            if signature != active_signature:
                active_signature = signature
                if runtime_settings.enable_daily_sync_scheduler:
                    next_run = next_run_datetime(now, runtime_settings.daily_sync_cron)
                    logger.info(
                        "Daily sync scheduler enabled. Cron='%s', next run at %s.",
                        runtime_settings.daily_sync_cron,
                        next_run.isoformat(),
                    )
                else:
                    next_run = None
                    logger.info("Daily sync scheduler disabled by runtime settings.")

            if not runtime_settings.enable_daily_sync_scheduler:
                if await self._wait_or_stop(30):
                    break
                continue

            if next_run is None:
                next_run = next_run_datetime(now, runtime_settings.daily_sync_cron)

            if now < next_run:
                wait_seconds = min((next_run - now).total_seconds(), 30)
                if await self._wait_or_stop(wait_seconds):
                    break
                continue

            await self.enqueue_sync_jobs_for_all_accounts()
            next_run = next_run_datetime(
                datetime.now().astimezone(),
                runtime_settings.daily_sync_cron,
            )

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

    async def _get_runtime_settings(self):
        try:
            async with self.session_factory() as session:
                service = AppSettingsService(session)
                return await service.get_runtime_settings()
        except Exception:
            settings = get_settings()
            logger.exception(
                "Failed to read runtime settings from database. Falling back to .env defaults."
            )
            return RuntimeSettings(
                enable_daily_sync_scheduler=settings.enable_daily_sync_scheduler,
                daily_sync_cron=settings.daily_sync_cron,
            )

    async def _wait_or_stop(self, timeout_seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(timeout_seconds, 0))
            return True
        except asyncio.TimeoutError:
            return False
