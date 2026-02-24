"""In-memory tracking for provider API request usage."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


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

    @staticmethod
    def _normalize_provider(provider: str | None) -> str:
        candidate = (provider or "").strip().lower()
        return candidate if candidate else "unknown"

    def _prune(self, counter: _ProviderCounter, now: datetime) -> None:
        floor = now - timedelta(seconds=self._max_window_seconds)
        while counter.recent_timestamps and counter.recent_timestamps[0] < floor:
            counter.recent_timestamps.popleft()

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

    async def snapshot(self, *, now: datetime | None = None) -> list[dict]:
        current = now or datetime.now(UTC)
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
