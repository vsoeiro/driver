"""In-memory tracking for provider API request usage."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional runtime dependency
    Redis = None  # type: ignore[assignment]

from backend.core.config import get_settings


@dataclass(frozen=True)
class ProviderRequestLimit:
    provider: str
    label: str
    max_requests: int
    window_seconds: int
    docs_url: str
    notes: str | None = None


@dataclass
class _ProviderCounter:
    total_requests: int = 0
    successful_responses: int = 0
    throttled_responses: int = 0
    client_error_responses: int = 0
    server_error_responses: int = 0
    timeout_errors: int = 0
    connection_errors: int = 0
    last_request_at: datetime | None = None
    # Keep only timestamps needed for the largest rolling window.
    recent_timestamps: deque[datetime] = field(default_factory=deque)


PROVIDER_LIMITS: dict[str, ProviderRequestLimit] = {
    # Source: https://developers.google.com/drive/api/guides/limits
    # "Queries per 60 seconds: 12,000"
    "google": ProviderRequestLimit(
        provider="google",
        label="Google Drive API",
        max_requests=12_000,
        window_seconds=60,
        docs_url="https://developers.google.com/drive/api/guides/limits",
        notes="Quota table also shows 12,000 per 60s per user.",
    ),
    # Source: https://learn.microsoft.com/graph/throttling-limits
    # Global Graph limit: "Any: 130,000 requests per 10 seconds (per app across all tenants)"
    "microsoft": ProviderRequestLimit(
        provider="microsoft",
        label="Microsoft Graph API",
        max_requests=130_000,
        window_seconds=10,
        docs_url="https://learn.microsoft.com/graph/throttling-limits",
        notes="This is the Graph global limit; service-specific limits may be lower.",
    ),
    # Source: https://developers.dropbox.com/dbx-performance-guide
    # Dropbox applies adaptive throttling rather than a single fixed public limit.
    # We track a conservative synthetic baseline window for utilization telemetry.
    "dropbox": ProviderRequestLimit(
        provider="dropbox",
        label="Dropbox API",
        max_requests=1_200,
        window_seconds=300,
        docs_url="https://developers.dropbox.com/dbx-performance-guide",
        notes="Adaptive rate limits; this baseline is for relative utilization tracking.",
    ),
}


class ProviderRequestUsageTracker:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counters: dict[str, _ProviderCounter] = {}
        self._max_window_seconds = max(
            (limit.window_seconds for limit in PROVIDER_LIMITS.values()),
            default=60,
        )
        self._redis_client: Redis | None = None
        self._redis_client_lock = asyncio.Lock()
        self._redis_key_prefix = "driver:provider_usage"

    @staticmethod
    def _normalize_provider(provider: str | None) -> str:
        candidate = (provider or "").strip().lower()
        return candidate if candidate else "unknown"

    def _prune(self, counter: _ProviderCounter, now: datetime) -> None:
        floor = now - timedelta(seconds=self._max_window_seconds)
        while counter.recent_timestamps and counter.recent_timestamps[0] < floor:
            counter.recent_timestamps.popleft()

    async def _get_redis_client(self) -> Redis | None:
        if Redis is None:
            return None
        if self._redis_client is not None:
            return self._redis_client
        async with self._redis_client_lock:
            if self._redis_client is not None:
                return self._redis_client
            try:
                settings = get_settings()
                client = Redis.from_url(settings.redis_url, decode_responses=True)
                await client.ping()
                self._redis_client = client
            except Exception:
                self._redis_client = None
            return self._redis_client

    async def _record_response_redis(
        self,
        *,
        provider: str,
        status_code: int,
        now: datetime,
    ) -> None:
        client = await self._get_redis_client()
        if client is None:
            return
        score = now.timestamp()
        providers_key = f"{self._redis_key_prefix}:providers"
        counts_key = f"{self._redis_key_prefix}:{provider}:counts"
        timestamps_key = f"{self._redis_key_prefix}:{provider}:timestamps"
        window_floor = score - float(self._max_window_seconds)
        member = f"{score}:{uuid4().hex}"

        fields = {"total_requests": 1, "successful_responses": 0, "throttled_responses": 0, "client_error_responses": 0, "server_error_responses": 0}
        if 200 <= status_code < 400:
            fields["successful_responses"] = 1
        elif status_code == 429:
            fields["throttled_responses"] = 1
        elif 400 <= status_code < 500:
            fields["client_error_responses"] = 1
        elif status_code >= 500:
            fields["server_error_responses"] = 1

        try:
            pipe = client.pipeline()
            pipe.sadd(providers_key, provider)
            for field, value in fields.items():
                if value:
                    pipe.hincrby(counts_key, field, value)
            pipe.hset(counts_key, "last_request_at", now.isoformat())
            pipe.zadd(timestamps_key, {member: score})
            pipe.zremrangebyscore(timestamps_key, "-inf", window_floor)
            await pipe.execute()
        except Exception:
            return

    async def _record_transport_error_redis(
        self,
        *,
        provider: str,
        kind: str,
        now: datetime,
    ) -> None:
        client = await self._get_redis_client()
        if client is None:
            return
        providers_key = f"{self._redis_key_prefix}:providers"
        counts_key = f"{self._redis_key_prefix}:{provider}:counts"
        field = "timeout_errors" if kind == "timeout" else "connection_errors"
        try:
            pipe = client.pipeline()
            pipe.sadd(providers_key, provider)
            pipe.hincrby(counts_key, field, 1)
            pipe.hset(counts_key, "last_request_at", now.isoformat())
            await pipe.execute()
        except Exception:
            return

    async def _snapshot_from_redis(self, *, now: datetime) -> list[dict] | None:
        client = await self._get_redis_client()
        if client is None:
            return None

        providers_key = f"{self._redis_key_prefix}:providers"
        try:
            redis_providers = {
                str(provider)
                for provider in await client.smembers(providers_key)
            }
        except Exception:
            return None

        providers = sorted(set(PROVIDER_LIMITS.keys()) | redis_providers)
        rows: list[dict] = []
        for provider in providers:
            limit = PROVIDER_LIMITS.get(provider)
            counts_key = f"{self._redis_key_prefix}:{provider}:counts"
            timestamps_key = f"{self._redis_key_prefix}:{provider}:timestamps"
            now_ts = now.timestamp()
            try:
                pipe = client.pipeline()
                pipe.hgetall(counts_key)
                if limit is not None:
                    floor = now_ts - float(limit.window_seconds)
                    pipe.zcount(timestamps_key, floor, now_ts)
                else:
                    pipe.zcard(timestamps_key)
                if limit is not None:
                    prune_floor = now_ts - float(self._max_window_seconds)
                    pipe.zremrangebyscore(timestamps_key, "-inf", prune_floor)
                result = await pipe.execute()
                counts = result[0] if isinstance(result[0], dict) else {}
                requests_in_window = int(result[1] or 0)
            except Exception:
                return None

            total_requests = int(counts.get("total_requests", 0) or 0)
            successful_responses = int(counts.get("successful_responses", 0) or 0)
            throttled_responses = int(counts.get("throttled_responses", 0) or 0)
            client_error_responses = int(counts.get("client_error_responses", 0) or 0)
            server_error_responses = int(counts.get("server_error_responses", 0) or 0)
            timeout_errors = int(counts.get("timeout_errors", 0) or 0)
            connection_errors = int(counts.get("connection_errors", 0) or 0)
            raw_last_request = counts.get("last_request_at")
            last_request_at = None
            if raw_last_request:
                try:
                    parsed = datetime.fromisoformat(str(raw_last_request))
                    last_request_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
                except Exception:
                    last_request_at = None

            utilization = 0.0
            if limit is not None and limit.max_requests > 0:
                utilization = requests_in_window / limit.max_requests

            rows.append(
                {
                    "provider": provider,
                    "provider_label": (limit.label if limit else provider.title()),
                    "window_seconds": (limit.window_seconds if limit else 0),
                    "max_requests": (limit.max_requests if limit else 0),
                    "requests_in_window": requests_in_window,
                    "utilization_ratio": max(0.0, min(utilization, 1.0)),
                    "docs_url": (limit.docs_url if limit else None),
                    "notes": (limit.notes if limit else None),
                    "total_requests_since_start": total_requests,
                    "successful_responses": successful_responses,
                    "throttled_responses": throttled_responses,
                    "client_error_responses": client_error_responses,
                    "server_error_responses": server_error_responses,
                    "timeout_errors": timeout_errors,
                    "connection_errors": connection_errors,
                    "last_request_at": last_request_at,
                }
            )
        return rows

    async def record_response(
        self,
        *,
        provider: str | None,
        status_code: int,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        key = self._normalize_provider(provider)
        async with self._lock:
            counter = self._counters.setdefault(key, _ProviderCounter())
            counter.total_requests += 1
            counter.last_request_at = current
            counter.recent_timestamps.append(current)
            if 200 <= status_code < 400:
                counter.successful_responses += 1
            elif status_code == 429:
                counter.throttled_responses += 1
            elif 400 <= status_code < 500:
                counter.client_error_responses += 1
            elif status_code >= 500:
                counter.server_error_responses += 1
            self._prune(counter, current)
        await self._record_response_redis(
            provider=key,
            status_code=status_code,
            now=current,
        )

    async def record_transport_error(
        self,
        *,
        provider: str | None,
        kind: str,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        key = self._normalize_provider(provider)
        async with self._lock:
            counter = self._counters.setdefault(key, _ProviderCounter())
            counter.last_request_at = current
            if kind == "timeout":
                counter.timeout_errors += 1
            else:
                counter.connection_errors += 1
            self._prune(counter, current)
        await self._record_transport_error_redis(
            provider=key,
            kind=kind,
            now=current,
        )

    async def snapshot(self, *, now: datetime | None = None) -> list[dict]:
        current = now or datetime.now(UTC)
        redis_rows = await self._snapshot_from_redis(now=current)
        if redis_rows is not None:
            return redis_rows
        async with self._lock:
            providers = sorted(set(PROVIDER_LIMITS.keys()) | set(self._counters.keys()))
            rows: list[dict] = []
            for provider in providers:
                limit = PROVIDER_LIMITS.get(provider)
                counter = self._counters.setdefault(provider, _ProviderCounter())
                self._prune(counter, current)

                requests_in_window = 0
                if limit is not None:
                    floor = current - timedelta(seconds=limit.window_seconds)
                    requests_in_window = sum(
                        1 for ts in counter.recent_timestamps if ts >= floor
                    )
                    utilization = (
                        requests_in_window / limit.max_requests
                        if limit.max_requests > 0
                        else 0.0
                    )
                else:
                    utilization = 0.0

                rows.append(
                    {
                        "provider": provider,
                        "provider_label": (limit.label if limit else provider.title()),
                        "window_seconds": (limit.window_seconds if limit else 0),
                        "max_requests": (limit.max_requests if limit else 0),
                        "requests_in_window": requests_in_window,
                        "utilization_ratio": max(0.0, min(utilization, 1.0)),
                        "docs_url": (limit.docs_url if limit else None),
                        "notes": (limit.notes if limit else None),
                        "total_requests_since_start": counter.total_requests,
                        "successful_responses": counter.successful_responses,
                        "throttled_responses": counter.throttled_responses,
                        "client_error_responses": counter.client_error_responses,
                        "server_error_responses": counter.server_error_responses,
                        "timeout_errors": counter.timeout_errors,
                        "connection_errors": counter.connection_errors,
                        "last_request_at": counter.last_request_at,
                    }
                )
            return rows


provider_request_usage_tracker = ProviderRequestUsageTracker()
