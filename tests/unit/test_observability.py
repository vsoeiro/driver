from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas.admin import ObservabilitySnapshot
from backend.services.observability import ObservabilityService, clear_observability_cache


def _snapshot(now: datetime) -> ObservabilitySnapshot:
    return ObservabilitySnapshot(
        generated_at=now,
        queue_depth=1,
        pending_jobs=1,
        running_jobs=1,
        retry_scheduled_jobs=0,
        throughput_last_hour=1,
        throughput_window=1,
        throughput_last_24h=1,
        success_rate_window=1.0,
        success_rate_last_24h=1.0,
        dead_letter_jobs_window=0,
        dead_letter_jobs_24h=0,
    )


def test_normalize_period_pick_number_extract_summary_and_p95():
    service = ObservabilityService(AsyncMock())

    assert service.normalize_period("7d") == ("7d", 168)
    assert service.normalize_period("invalid") == ("24h", 24)
    assert service._pick_number({"value": True, "count": 4.8}, ["value", "count"]) == 4
    assert service._pick_number(None, ["count"]) == 0
    assert service._extract_job_metric_summary(
        SimpleNamespace(metrics={"total": 10, "mapped": 8}, result={"errors": 2, "unchanged": 1})
    ) == {"total": 10, "success": 8, "failed": 2, "skipped": 1}
    assert service._p95([]) is None
    assert service._p95([1.0, 2.0, 3.0, 9.0]) == 9.0


@pytest.mark.asyncio
async def test_observability_cache_store_get_and_clear():
    service = ObservabilityService(AsyncMock())
    now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
    snapshot = _snapshot(now)

    await clear_observability_cache()
    await service._store_cached_snapshot(period_key="24h", snapshot=snapshot, expires_at=now + timedelta(seconds=20))

    cached = await service._get_cached_snapshot(period_key="24h", now=now)
    assert cached is not None
    assert cached.cache_hit is True

    await clear_observability_cache()
    assert await service._get_cached_snapshot(period_key="24h", now=now) is None


@pytest.mark.asyncio
async def test_build_alerts_returns_expected_operational_alerts():
    session = AsyncMock()
    now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
    session.scalar.return_value = now - timedelta(minutes=31)
    service = ObservabilityService(session)

    with patch("backend.services.observability.log_event") as log_event:
        alerts = await service._build_alerts(
            now=now,
            redis_ok=False,
            retry_count=11,
            dead_letter_window=2,
            running_count=1,
            failures_last_hour=2,
            finalized_last_hour=6,
            period_label="24h",
        )

    assert {alert.code for alert in alerts} == {
        "redis_unavailable",
        "dead_letter_detected",
        "retry_backlog",
        "high_failure_rate",
        "stuck_running_jobs",
    }
    assert log_event.call_count == 5


@pytest.mark.asyncio
async def test_snapshot_uses_cache_and_marks_force_refresh_as_miss():
    session = AsyncMock()
    service = ObservabilityService(session)
    now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
    fresh_snapshot = _snapshot(now)

    with patch("backend.services.observability.datetime") as datetime_mock:
        datetime_mock.now.return_value = now
        datetime_mock.side_effect = datetime
        service._build_snapshot = AsyncMock(return_value=fresh_snapshot)

        first = await service.snapshot(period="24h")
        second = await service.snapshot(period="24h")
        forced = await service.snapshot(period="24h", force_refresh=True)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert forced.cache_hit is False
    assert service._build_snapshot.await_count == 2
