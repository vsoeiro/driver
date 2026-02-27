"""Operational observability metrics for admin dashboards."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging_utils import log_event
from backend.db.models import AIChatMessage, AIToolCall, Job, LinkedAccount
from backend.schemas.admin import (
    DeadLetterJobSummary,
    IntegrationHealthStatus,
    ObservabilityAlert,
    ObservabilitySnapshot,
)
from backend.services.app_settings import AppSettingsService
from backend.services.job_queue import get_job_queue
from backend.services.provider_request_usage import provider_request_usage_tracker

logger = logging.getLogger(__name__)

PERIOD_WINDOW_HOURS: dict[str, int] = {
    "24h": 24,
    "3d": 72,
    "7d": 168,
    "30d": 720,
    "90d": 2160,
}
DEFAULT_PERIOD_KEY = "24h"
OBSERVABILITY_CACHE_TTL_SECONDS = 20


@dataclass
class _SnapshotCacheEntry:
    snapshot: ObservabilitySnapshot
    expires_at: datetime


_snapshot_cache: dict[str, _SnapshotCacheEntry] = {}
_snapshot_cache_lock: asyncio.Lock | None = None


async def clear_observability_cache() -> None:
    """Invalidate in-memory observability snapshots."""
    global _snapshot_cache_lock
    if _snapshot_cache_lock is None:
        _snapshot_cache_lock = asyncio.Lock()
    async with _snapshot_cache_lock:
        _snapshot_cache.clear()


class ObservabilityService:
    """Build operational metrics and basic alerts for admin usage."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def normalize_period(period: str | None) -> tuple[str, int]:
        candidate = (period or DEFAULT_PERIOD_KEY).strip().lower()
        if candidate not in PERIOD_WINDOW_HOURS:
            candidate = DEFAULT_PERIOD_KEY
        return candidate, PERIOD_WINDOW_HOURS[candidate]

    async def snapshot(
        self,
        *,
        period: str | None = None,
        force_refresh: bool = False,
    ) -> ObservabilitySnapshot:
        period_key, period_hours = self.normalize_period(period)
        now = datetime.now(UTC)

        if not force_refresh:
            cached = await self._get_cached_snapshot(period_key=period_key, now=now)
            if cached is not None:
                return cached

        snapshot = await self._build_snapshot(
            now=now,
            period_key=period_key,
            period_hours=period_hours,
        )
        expires_at = now + timedelta(seconds=OBSERVABILITY_CACHE_TTL_SECONDS)
        snapshot.cache_hit = False
        snapshot.cache_ttl_seconds = OBSERVABILITY_CACHE_TTL_SECONDS
        snapshot.cache_expires_at = expires_at

        await self._store_cached_snapshot(
            period_key=period_key,
            snapshot=snapshot,
            expires_at=expires_at,
        )
        return snapshot

    async def _get_cached_snapshot(self, *, period_key: str, now: datetime) -> ObservabilitySnapshot | None:
        global _snapshot_cache_lock
        if _snapshot_cache_lock is None:
            _snapshot_cache_lock = asyncio.Lock()
        async with _snapshot_cache_lock:
            entry = _snapshot_cache.get(period_key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                _snapshot_cache.pop(period_key, None)
                return None
            snapshot = entry.snapshot.model_copy(deep=True)
            snapshot.cache_hit = True
            snapshot.cache_expires_at = entry.expires_at
            snapshot.cache_ttl_seconds = max(0, int((entry.expires_at - now).total_seconds()))
            return snapshot

    async def _store_cached_snapshot(
        self,
        *,
        period_key: str,
        snapshot: ObservabilitySnapshot,
        expires_at: datetime,
    ) -> None:
        global _snapshot_cache_lock
        if _snapshot_cache_lock is None:
            _snapshot_cache_lock = asyncio.Lock()
        async with _snapshot_cache_lock:
            _snapshot_cache[period_key] = _SnapshotCacheEntry(
                snapshot=snapshot.model_copy(deep=True),
                expires_at=expires_at,
            )

    async def _build_snapshot(
        self,
        *,
        now: datetime,
        period_key: str,
        period_hours: int,
    ) -> ObservabilitySnapshot:
        period_start = now - timedelta(hours=period_hours)
        hour_ago = now - timedelta(hours=1)
        period_label = period_key

        queue = get_job_queue()
        redis_ok = True
        redis_detail = "Redis reachable"
        queue_depth = 0
        try:
            if hasattr(queue, "queued_jobs"):
                queue_depth = int(await queue.queued_jobs())
            if hasattr(queue, "ping"):
                await queue.ping()
        except Exception as exc:
            redis_ok = False
            redis_detail = str(exc)

        pending_count = await self.session.scalar(select(func.count(Job.id)).where(Job.status == "PENDING")) or 0
        running_count = await self.session.scalar(select(func.count(Job.id)).where(Job.status == "RUNNING")) or 0
        retry_count = await self.session.scalar(select(func.count(Job.id)).where(Job.status == "RETRY_SCHEDULED")) or 0

        finalized_stmt = select(Job).where(
            Job.completed_at.is_not(None),
            Job.completed_at >= period_start,
            Job.status.in_(["COMPLETED", "FAILED", "DEAD_LETTER", "CANCELLED"]),
        )
        recent_finalized = (await self.session.execute(finalized_stmt)).scalars().all()

        durations: list[float] = []
        success_count = 0
        dead_letter_window = 0
        throughput_last_hour = 0
        failures_last_hour = 0
        finalized_last_hour = 0
        metrics_total_window = 0
        metrics_success_window = 0
        metrics_failed_window = 0
        metrics_skipped_window = 0

        for job in recent_finalized:
            if job.started_at and job.completed_at:
                durations.append(max(0.0, (job.completed_at - job.started_at).total_seconds()))
            if job.status == "COMPLETED":
                success_count += 1
            if job.status == "DEAD_LETTER":
                dead_letter_window += 1
            if job.completed_at and job.completed_at >= hour_ago:
                throughput_last_hour += 1
                finalized_last_hour += 1
                if job.status in {"FAILED", "DEAD_LETTER"}:
                    failures_last_hour += 1
            metric_summary = self._extract_job_metric_summary(job)
            metrics_total_window += metric_summary["total"]
            metrics_success_window += metric_summary["success"]
            metrics_failed_window += metric_summary["failed"]
            metrics_skipped_window += metric_summary["skipped"]

        throughput_window = len(recent_finalized)
        success_rate_window = (success_count / throughput_window) if throughput_window > 0 else 1.0
        avg_duration = (sum(durations) / len(durations)) if durations else None
        p95_duration = self._p95(durations)

        accounts = (await self.session.execute(select(LinkedAccount))).scalars().all()
        active_accounts = [acc for acc in accounts if acc.is_active]
        provider_counts: dict[str, int] = {}
        for account in active_accounts:
            provider_counts[account.provider] = provider_counts.get(account.provider, 0) + 1

        runtime = await AppSettingsService(self.session).get_runtime_settings()
        ai_messages_window = (
            await self.session.scalar(
                select(func.count(AIChatMessage.id)).where(
                    AIChatMessage.created_at >= period_start,
                    AIChatMessage.role == "user",
                )
            )
            or 0
        )
        ai_tool_calls_window = (
            await self.session.scalar(
                select(func.count(AIToolCall.id)).where(
                    AIToolCall.created_at >= period_start,
                )
            )
            or 0
        )
        ai_failed_tool_calls_window = (
            await self.session.scalar(
                select(func.count(AIToolCall.id)).where(
                    AIToolCall.created_at >= period_start,
                    AIToolCall.status != "success",
                )
            )
            or 0
        )

        ai_status = "ok" if int(ai_messages_window) > 0 or int(ai_tool_calls_window) > 0 else "warning"
        if int(ai_failed_tool_calls_window) > 0:
            ai_status = "warning"
        integration_health = [
            IntegrationHealthStatus(
                key="redis",
                label="Redis Queue",
                status="ok" if redis_ok else "error",
                detail=redis_detail,
            ),
            IntegrationHealthStatus(
                key="scheduler",
                label="Daily Scheduler",
                status="ok" if runtime.enable_daily_sync_scheduler else "warning",
                detail=f"enabled={runtime.enable_daily_sync_scheduler}, cron='{runtime.daily_sync_cron}'",
            ),
            IntegrationHealthStatus(
                key="accounts",
                label="Linked Accounts",
                status="ok" if len(active_accounts) > 0 else "warning",
                detail=f"active={len(active_accounts)} by_provider={provider_counts}",
            ),
            IntegrationHealthStatus(
                key="ai_usage",
                label="AI Usage",
                status=ai_status,
                detail=(
                    f"mode={runtime.ai_provider_mode}, model='{runtime.ai_model_default}', "
                    f"user_messages={int(ai_messages_window)}, tool_calls={int(ai_tool_calls_window)}, "
                    f"failed_tool_calls={int(ai_failed_tool_calls_window)}"
                ),
            ),
        ]

        alerts = await self._build_alerts(
            now=now,
            redis_ok=redis_ok,
            retry_count=retry_count,
            dead_letter_window=dead_letter_window,
            running_count=running_count,
            failures_last_hour=failures_last_hour,
            finalized_last_hour=finalized_last_hour,
            period_label=period_label,
        )

        dead_letter_rows = await self.session.execute(
            select(Job)
            .where(Job.status == "DEAD_LETTER")
            .order_by(Job.dead_lettered_at.desc().nullslast(), Job.completed_at.desc().nullslast())
            .limit(10)
        )
        dead_letter_jobs = [
            DeadLetterJobSummary(
                id=row.id,
                type=row.type,
                dead_lettered_at=row.dead_lettered_at,
                dead_letter_reason=row.dead_letter_reason,
                retry_count=row.retry_count,
                max_retries=row.max_retries,
            )
            for row in dead_letter_rows.scalars().all()
        ]
        provider_request_usage = await provider_request_usage_tracker.snapshot(now=now)

        return ObservabilitySnapshot(
            generated_at=now,
            period_key=period_key,
            period_label=period_label,
            period_hours=period_hours,
            queue_depth=queue_depth,
            pending_jobs=int(pending_count),
            running_jobs=int(running_count),
            retry_scheduled_jobs=int(retry_count),
            throughput_last_hour=throughput_last_hour,
            throughput_window=throughput_window,
            throughput_last_24h=throughput_window,
            success_rate_window=round(success_rate_window, 4),
            success_rate_last_24h=round(success_rate_window, 4),
            avg_duration_seconds_window=round(avg_duration, 2) if avg_duration is not None else None,
            avg_duration_seconds_last_24h=round(avg_duration, 2) if avg_duration is not None else None,
            p95_duration_seconds_window=round(p95_duration, 2) if p95_duration is not None else None,
            p95_duration_seconds_last_24h=round(p95_duration, 2) if p95_duration is not None else None,
            dead_letter_jobs_window=dead_letter_window,
            dead_letter_jobs_24h=dead_letter_window,
            metrics_total_window=metrics_total_window,
            metrics_success_window=metrics_success_window,
            metrics_failed_window=metrics_failed_window,
            metrics_skipped_window=metrics_skipped_window,
            metrics_total_24h=metrics_total_window,
            metrics_success_24h=metrics_success_window,
            metrics_failed_24h=metrics_failed_window,
            metrics_skipped_24h=metrics_skipped_window,
            recent_alerts=alerts,
            integration_health=integration_health,
            dead_letter_jobs=dead_letter_jobs,
            provider_request_usage=provider_request_usage,
        )

    @staticmethod
    def _pick_number(source: dict[str, Any] | None, keys: list[str]) -> int:
        if not isinstance(source, dict):
            return 0
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return int(value)
        return 0

    def _extract_job_metric_summary(self, job: Job) -> dict[str, int]:
        metrics = job.metrics if isinstance(job.metrics, dict) else {}
        result = job.result if isinstance(job.result, dict) else {}
        return {
            "total": self._pick_number(metrics, ["total"]) or self._pick_number(result, ["total"]),
            "success": (
                self._pick_number(metrics, ["success", "mapped", "updated", "changed"])
                or self._pick_number(result, ["success", "mapped", "updated", "changed"])
            ),
            "failed": (
                self._pick_number(metrics, ["failed", "errors"])
                or self._pick_number(result, ["failed", "errors"])
            ),
            "skipped": (
                self._pick_number(metrics, ["skipped", "unchanged"])
                or self._pick_number(result, ["skipped", "unchanged"])
            ),
        }

    async def _build_alerts(
        self,
        *,
        now: datetime,
        redis_ok: bool,
        retry_count: int,
        dead_letter_window: int,
        running_count: int,
        failures_last_hour: int,
        finalized_last_hour: int,
        period_label: str,
    ) -> list[ObservabilityAlert]:
        alerts: list[ObservabilityAlert] = []

        if not redis_ok:
            alerts.append(
                ObservabilityAlert(
                    severity="critical",
                    code="redis_unavailable",
                    message="Redis queue is unavailable. New/retry jobs may not be processed.",
                    created_at=now,
                )
            )

        if dead_letter_window > 0:
            alerts.append(
                ObservabilityAlert(
                    severity="warning",
                    code="dead_letter_detected",
                    message=f"{dead_letter_window} job(s) reached dead-letter in the selected period ({period_label}).",
                    created_at=now,
                )
            )

        if retry_count >= 10:
            alerts.append(
                ObservabilityAlert(
                    severity="warning",
                    code="retry_backlog",
                    message=f"{retry_count} job(s) currently waiting for retry.",
                    created_at=now,
                )
            )

        if finalized_last_hour >= 5:
            failure_rate = failures_last_hour / max(1, finalized_last_hour)
            if failure_rate >= 0.25:
                alerts.append(
                    ObservabilityAlert(
                        severity="warning",
                        code="high_failure_rate",
                        message=(
                            f"High failure rate in the last hour: "
                            f"{failures_last_hour}/{finalized_last_hour} ({failure_rate:.0%})."
                        ),
                        created_at=now,
                    )
                )

        if running_count > 0:
            oldest_running = await self.session.scalar(
                select(func.min(Job.started_at)).where(
                    Job.status == "RUNNING",
                    Job.started_at.is_not(None),
                )
            )
            if oldest_running and (now - oldest_running) >= timedelta(minutes=30):
                alerts.append(
                    ObservabilityAlert(
                        severity="critical",
                        code="stuck_running_jobs",
                        message="There are RUNNING jobs older than 30 minutes.",
                        created_at=now,
                    )
                )

        for alert in alerts:
            if alert.severity in {"warning", "critical"}:
                level = logging.ERROR if alert.severity == "critical" else logging.WARNING
                log_event(
                    logger,
                    "operational_alert",
                    level=level,
                    code=alert.code,
                    severity=alert.severity,
                    message=alert.message,
                )

        return alerts

    @staticmethod
    def _p95(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95))))
        return ordered[index]
