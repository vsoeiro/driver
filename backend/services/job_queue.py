"""Redis-backed job queue abstraction using ARQ."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Protocol

from arq.connections import RedisSettings, create_pool

from backend.core.config import get_settings


class JobQueue(Protocol):
    """Queue contract for background job dispatch."""

    async def enqueue_job(self, job_id: str, *, defer_seconds: int = 0) -> None: ...
    async def queued_jobs(self) -> int: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class RedisJobQueue:
    """ARQ-based queue implementation."""

    def __init__(self, redis_dsn: str, queue_name: str) -> None:
        self._redis_dsn = redis_dsn
        self._queue_name = queue_name
        self._pool = None
        self._lock = asyncio.Lock()

    async def _get_pool(self):
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is None:
                settings = RedisSettings.from_dsn(self._redis_dsn)
                self._pool = await create_pool(settings)
        return self._pool

    async def enqueue_job(self, job_id: str, *, defer_seconds: int = 0) -> None:
        pool = await self._get_pool()
        kwargs = {"_queue_name": self._queue_name}
        if defer_seconds > 0:
            kwargs["_defer_by"] = timedelta(seconds=defer_seconds)
        await pool.enqueue_job("process_job", str(job_id), **kwargs)

    async def queued_jobs(self) -> int:
        pool = await self._get_pool()
        return int(await pool.zcard(self._queue_name))

    async def ping(self) -> bool:
        pool = await self._get_pool()
        await pool.ping()
        return True

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


_queue_singleton: RedisJobQueue | None = None


def get_job_queue() -> RedisJobQueue:
    global _queue_singleton
    if _queue_singleton is None:
        settings = get_settings()
        _queue_singleton = RedisJobQueue(
            redis_dsn=settings.redis_url,
            queue_name=settings.redis_queue_name,
        )
    return _queue_singleton


async def close_job_queue() -> None:
    global _queue_singleton
    if _queue_singleton is not None:
        await _queue_singleton.close()
        _queue_singleton = None
