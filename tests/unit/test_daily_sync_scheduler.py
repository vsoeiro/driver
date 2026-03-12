from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.services.cron_utils import seconds_until_next_run
from backend.services.app_settings import RuntimeSettings
from backend.services.sync_scheduler import DailySyncScheduler


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_seconds_until_next_run_same_day():
    now = datetime(2026, 2, 15, 23, 50, 0, tzinfo=UTC)
    seconds = seconds_until_next_run(now, "55 23 * * *")
    assert seconds == 300


def test_seconds_until_next_run_next_day():
    now = datetime(2026, 2, 15, 23, 50, 0, tzinfo=UTC)
    seconds = seconds_until_next_run(now, "0 0 * * *")
    assert seconds == 600


@pytest.mark.asyncio
async def test_enqueue_sync_jobs_for_all_accounts():
    account_ids = [uuid4(), uuid4(), uuid4()]

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = account_ids
    session.execute.return_value = result

    session_factory = MagicMock(return_value=_SessionContext(session))
    scheduler = DailySyncScheduler(session_factory)

    with patch("backend.services.sync_scheduler.JobService.create_job", new_callable=AsyncMock) as create_job:
        created_count = await scheduler.enqueue_sync_jobs_for_all_accounts()

    assert created_count == 3
    assert create_job.await_count == 3


@pytest.mark.asyncio
async def test_get_runtime_settings_falls_back_to_env_defaults():
    session_factory = MagicMock(side_effect=RuntimeError("db unavailable"))
    scheduler = DailySyncScheduler(session_factory)

    fake_settings = MagicMock(
        enable_daily_sync_scheduler=True,
        daily_sync_cron="0 1 * * *",
        worker_job_timeout_seconds=900,
    )

    with patch("backend.services.sync_scheduler.get_settings", return_value=fake_settings):
        runtime = await scheduler._get_runtime_settings()

    assert isinstance(runtime, RuntimeSettings)
    assert runtime.daily_sync_cron == "0 1 * * *"
    assert runtime.worker_job_timeout_seconds == 900


@pytest.mark.asyncio
async def test_wait_or_stop_returns_true_when_stop_event_is_set():
    scheduler = DailySyncScheduler(MagicMock())
    scheduler.stop()

    assert await scheduler._wait_or_stop(0.1) is True


@pytest.mark.asyncio
async def test_wait_or_stop_returns_false_on_timeout():
    scheduler = DailySyncScheduler(MagicMock())

    assert await scheduler._wait_or_stop(0.01) is False


class _FakeRedisClient:
    def __init__(self):
        self.current_value = None
        self.expire_calls = []
        self.set_calls = []
        self.eval_calls = []
        self.closed = False

    async def get(self, key):
        return self.current_value if key else None

    async def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))

    async def set(self, key, value, ex, nx):
        self.set_calls.append((key, value, ex, nx))
        self.current_value = value
        return True

    async def eval(self, script, key_count, key, owner):
        self.eval_calls.append((script, key_count, key, owner))

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_leader_lock_acquire_renew_release_and_close():
    scheduler = DailySyncScheduler(MagicMock())
    scheduler._lock_enabled = True
    scheduler._lock_key = "driver:test-lock"
    scheduler._lock_ttl_seconds = 30
    scheduler._lock_owner = "owner-1"
    scheduler._lock_client = _FakeRedisClient()

    acquired = await scheduler._acquire_or_renew_leader_lock()
    assert acquired is True
    assert scheduler._lock_is_owned is True
    assert scheduler._lock_client.set_calls == [("driver:test-lock", "owner-1", 30, True)]

    scheduler._lock_client.current_value = "owner-1"
    renewed = await scheduler._acquire_or_renew_leader_lock()
    assert renewed is True
    assert scheduler._lock_client.expire_calls == [("driver:test-lock", 30)]

    await scheduler._release_leader_lock()
    assert scheduler._lock_is_owned is False
    assert scheduler._lock_client.eval_calls

    client = scheduler._lock_client
    await scheduler._close_lock_client()
    assert client.closed is True
    assert scheduler._lock_client is None


@pytest.mark.asyncio
async def test_acquire_leader_lock_returns_false_when_redis_is_unavailable():
    scheduler = DailySyncScheduler(MagicMock())
    scheduler._lock_enabled = True

    with patch("backend.services.sync_scheduler.Redis", None):
        assert await scheduler._acquire_or_renew_leader_lock() is False
