"""Redis-backed job queue abstraction using ARQ."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Protocol

from arq.connections import RedisSettings, create_pool

from backend.core.config import get_settings


DEFAULT_QUEUE_ALIAS_SUFFIXES: dict[str, str] = {
    "default": "",
    "sync": "light",
    "io": "",
    "metadata": "",
    "rules": "",
    "comics": "heavy",
}


def build_queue_alias_map(*, settings=None) -> dict[str, str]:
    """Build queue alias -> queue name mapping from settings."""
    settings = settings or get_settings()
    base_queue_name = settings.redis_queue_name.strip() or "driver:jobs"
    aliases: dict[str, str] = {}
    for alias, suffix in DEFAULT_QUEUE_ALIAS_SUFFIXES.items():
        if alias == "default":
            aliases[alias] = base_queue_name
        elif suffix == "":
            aliases[alias] = base_queue_name
        else:
            aliases[alias] = f"{base_queue_name}:{suffix}"

    for alias, queue_name in (settings.job_queue_names or {}).items():
        normalized_alias = str(alias).strip().lower()
        normalized_queue_name = str(queue_name).strip()
        if normalized_alias and normalized_queue_name:
            aliases[normalized_alias] = normalized_queue_name

    aliases.setdefault("default", base_queue_name)
    return aliases


def resolve_queue_name(queue_alias_or_name: str | None, *, settings=None) -> str:
    """Resolve queue alias/name to a concrete Redis queue name."""
    aliases = build_queue_alias_map(settings=settings)
    if queue_alias_or_name is None:
        return aliases["default"]
    candidate = str(queue_alias_or_name).strip()
    if not candidate:
        return aliases["default"]
    return aliases.get(candidate.lower(), candidate)


def build_known_queue_names(*, settings=None) -> set[str]:
    """Return queue names known by aliases and type overrides."""
    settings = settings or get_settings()
    known_queue_names = {name for name in build_queue_alias_map(settings=settings).values() if name}
    for queue_alias_or_name in (settings.job_type_queue_map or {}).values():
        resolved = resolve_queue_name(str(queue_alias_or_name), settings=settings)
        if resolved:
            known_queue_names.add(resolved)
    return known_queue_names


class JobQueue(Protocol):
    """Queue contract for background job dispatch."""

    async def enqueue_job(
        self,
        job_id: str,
        *,
        queue_name: str | None = None,
        defer_seconds: int = 0,
    ) -> None: ...
    async def queued_jobs(self, *, queue_name: str | None = None) -> int: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class RedisJobQueue:
    """ARQ-based queue implementation."""

    def __init__(self, redis_dsn: str, queue_name: str, *, known_queue_names: set[str] | None = None) -> None:
        self._redis_dsn = redis_dsn
        self._queue_name = queue_name.strip() or "driver:jobs"
        known = {self._queue_name}
        known.update({str(name).strip() for name in (known_queue_names or set()) if str(name).strip()})
        self._known_queue_names = known
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

    @staticmethod
    def _normalize_queue_name(queue_name: str | None, default_queue_name: str) -> str:
        if queue_name is None:
            return default_queue_name
        normalized = str(queue_name).strip()
        return normalized or default_queue_name

    async def enqueue_job(
        self,
        job_id: str,
        *,
        queue_name: str | None = None,
        defer_seconds: int = 0,
    ) -> None:
        pool = await self._get_pool()
        target_queue_name = self._normalize_queue_name(queue_name, self._queue_name)
        kwargs = {"_queue_name": target_queue_name}
        if defer_seconds > 0:
            kwargs["_defer_by"] = timedelta(seconds=defer_seconds)
        await pool.enqueue_job("process_job", str(job_id), **kwargs)

    async def queued_jobs(self, *, queue_name: str | None = None) -> int:
        pool = await self._get_pool()
        if queue_name is not None:
            target_queue_name = self._normalize_queue_name(queue_name, self._queue_name)
            return int(await pool.zcard(target_queue_name))

        total = 0
        for known_queue_name in self._known_queue_names:
            total += int(await pool.zcard(known_queue_name))
        return total

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
            queue_name=resolve_queue_name(None, settings=settings),
            known_queue_names=build_known_queue_names(settings=settings),
        )
    return _queue_singleton


async def close_job_queue() -> None:
    global _queue_singleton
    if _queue_singleton is not None:
        await _queue_singleton.close()
        _queue_singleton = None
