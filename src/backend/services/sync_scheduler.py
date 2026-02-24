"""Daily scheduler to enqueue sync jobs for all active accounts."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.config import get_settings
from backend.services.app_settings import AppSettingsService, RuntimeSettings
from backend.services.cron_utils import next_run_datetime
from backend.db.models import LinkedAccount
from backend.schemas.jobs import JobCreate
from backend.services.jobs import JobService

logger = logging.getLogger(__name__)

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - import guard for constrained runtimes
    Redis = None  # type: ignore[assignment]


class DailySyncScheduler:
    """Enqueue one sync job per active account based on persisted cron settings."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory
        self._running = False
        self._stop_event = asyncio.Event()
        settings = get_settings()
        self._lock_enabled = bool(settings.scheduler_distributed_lock_enabled)
        self._lock_key = settings.scheduler_lock_key
        self._lock_ttl_seconds = int(settings.scheduler_lock_ttl_seconds)
        self._lock_owner = str(uuid4())
        self._lock_client: Redis | None = None
        self._lock_is_owned = False

    async def start(self) -> None:
        """Run the scheduling loop until stopped."""
        self._running = True
        logger.info("Daily sync scheduler started.")
        active_signature: tuple[bool, str] | None = None
        next_run: datetime | None = None

        while self._running:
            if not await self._acquire_or_renew_leader_lock():
                if await self._wait_or_stop(10):
                    break
                continue

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
        await self._release_leader_lock()
        await self._close_lock_client()

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
                worker_job_timeout_seconds=settings.worker_job_timeout_seconds,
            )

    async def _wait_or_stop(self, timeout_seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(timeout_seconds, 0))
            return True
        except asyncio.TimeoutError:
            return False

    async def _acquire_or_renew_leader_lock(self) -> bool:
        if not self._lock_enabled:
            return True
        if Redis is None:
            logger.error("Redis package unavailable; scheduler distributed lock is enabled.")
            return False

        try:
            client = await self._get_lock_client()
            if self._lock_is_owned:
                current = await client.get(self._lock_key)
                if current == self._lock_owner:
                    await client.expire(self._lock_key, self._lock_ttl_seconds)
                    return True
                self._lock_is_owned = False

            acquired = await client.set(
                self._lock_key,
                self._lock_owner,
                ex=self._lock_ttl_seconds,
                nx=True,
            )
            self._lock_is_owned = bool(acquired)
            if self._lock_is_owned:
                logger.debug("Acquired scheduler leader lock key=%s", self._lock_key)
            return self._lock_is_owned
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to acquire scheduler distributed lock: %s", exc)
            return False

    async def _release_leader_lock(self) -> None:
        if not self._lock_enabled or not self._lock_is_owned:
            return
        try:
            client = await self._get_lock_client()
            script = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""
            await client.eval(script, 1, self._lock_key, self._lock_owner)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to release scheduler distributed lock: %s", exc)
        finally:
            self._lock_is_owned = False

    async def _get_lock_client(self):
        if self._lock_client is not None:
            return self._lock_client
        settings = get_settings()
        self._lock_client = Redis.from_url(settings.redis_url, decode_responses=True)
        return self._lock_client

    async def _close_lock_client(self) -> None:
        if self._lock_client is None:
            return
        try:
            await self._lock_client.aclose()
        finally:
            self._lock_client = None
