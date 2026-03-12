from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.provider_request_usage import ProviderRequestUsageTracker


class _FakePipeline:
    def __init__(self, *, execute_result=None, should_raise: bool = False):
        self.commands: list[tuple] = []
        self.execute_result = execute_result or []
        self.should_raise = should_raise

    def sadd(self, *args):
        self.commands.append(("sadd", *args))
        return self

    def hincrby(self, *args):
        self.commands.append(("hincrby", *args))
        return self

    def hset(self, *args):
        self.commands.append(("hset", *args))
        return self

    def zadd(self, *args):
        self.commands.append(("zadd", *args))
        return self

    def zremrangebyscore(self, *args):
        self.commands.append(("zremrangebyscore", *args))
        return self

    def hgetall(self, *args):
        self.commands.append(("hgetall", *args))
        return self

    def zcount(self, *args):
        self.commands.append(("zcount", *args))
        return self

    def zcard(self, *args):
        self.commands.append(("zcard", *args))
        return self

    async def execute(self):
        if self.should_raise:
            raise RuntimeError("pipeline failed")
        return self.execute_result


class _FakeRedisClient:
    def __init__(self, *, pipeline_result=None, members=None, ping_error: Exception | None = None):
        self.pipeline_result = pipeline_result or []
        self.members = members or set()
        self.ping_error = ping_error
        self.pipeline_calls: list[_FakePipeline] = []

    async def ping(self):
        if self.ping_error:
            raise self.ping_error

    def pipeline(self):
        pipe = _FakePipeline(execute_result=self.pipeline_result)
        self.pipeline_calls.append(pipe)
        return pipe

    async def smembers(self, _key):
        return self.members


@pytest.mark.asyncio
async def test_record_response_and_snapshot_track_counts_and_windows():
    tracker = ProviderRequestUsageTracker()
    tracker._get_redis_client = AsyncMock(return_value=None)
    now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)

    await tracker.record_response(provider="google", status_code=200, now=now - timedelta(seconds=61))
    await tracker.record_response(provider="google", status_code=429, now=now)
    await tracker.record_response(provider="custom", status_code=503, now=now)
    await tracker.record_transport_error(provider="custom", kind="timeout", now=now)
    await tracker.record_transport_error(provider="custom", kind="connection", now=now)

    rows = await tracker.snapshot(now=now)
    google = next(row for row in rows if row["provider"] == "google")
    custom = next(row for row in rows if row["provider"] == "custom")

    assert google["total_requests_since_start"] == 2
    assert google["successful_responses"] == 1
    assert google["throttled_responses"] == 1
    assert google["requests_in_window"] == 1
    assert custom["server_error_responses"] == 1
    assert custom["timeout_errors"] == 1
    assert custom["connection_errors"] == 1
    assert custom["utilization_ratio"] == 0.0


@pytest.mark.asyncio
async def test_get_redis_client_caches_success_and_ignores_ping_failure():
    tracker = ProviderRequestUsageTracker()
    successful_client = _FakeRedisClient()

    with patch("backend.services.provider_request_usage.get_settings", return_value=type("S", (), {"redis_url": "redis://example"})()), \
        patch("backend.services.provider_request_usage.Redis", type("FakeRedis", (), {"from_url": staticmethod(lambda *_args, **_kwargs: successful_client)})):
        first = await tracker._get_redis_client()
        second = await tracker._get_redis_client()

    assert first is successful_client
    assert second is successful_client

    tracker = ProviderRequestUsageTracker()
    failing_client = _FakeRedisClient(ping_error=RuntimeError("down"))
    with patch("backend.services.provider_request_usage.get_settings", return_value=type("S", (), {"redis_url": "redis://example"})()), \
        patch("backend.services.provider_request_usage.Redis", type("FakeRedis", (), {"from_url": staticmethod(lambda *_args, **_kwargs: failing_client)})):
        client = await tracker._get_redis_client()

    assert client is None


@pytest.mark.asyncio
async def test_record_response_redis_and_transport_error_issue_pipeline_commands():
    tracker = ProviderRequestUsageTracker()
    client = _FakeRedisClient()
    tracker._get_redis_client = AsyncMock(return_value=client)
    now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)

    await tracker._record_response_redis(provider="google", status_code=429, now=now)
    await tracker._record_transport_error_redis(provider="google", kind="timeout", now=now)

    first_commands = client.pipeline_calls[0].commands
    second_commands = client.pipeline_calls[1].commands

    assert any(command[0] == "hincrby" and command[2] == "throttled_responses" for command in first_commands)
    assert any(command[0] == "zadd" for command in first_commands)
    assert any(command[0] == "hincrby" and command[2] == "timeout_errors" for command in second_commands)


@pytest.mark.asyncio
async def test_snapshot_from_redis_builds_rows_and_parses_last_request():
    tracker = ProviderRequestUsageTracker()
    now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
    client = _FakeRedisClient(
        pipeline_result=[
            {
                "total_requests": "10",
                "successful_responses": "8",
                "throttled_responses": "1",
                "client_error_responses": "0",
                "server_error_responses": "1",
                "timeout_errors": "2",
                "connection_errors": "1",
                "last_request_at": "2026-03-11T11:59:00",
            },
            12000,
            0,
        ],
        members={"custom"},
    )
    tracker._get_redis_client = AsyncMock(return_value=client)

    rows = await tracker._snapshot_from_redis(now=now)
    google = next(row for row in rows if row["provider"] == "google")
    custom = next(row for row in rows if row["provider"] == "custom")

    assert google["requests_in_window"] == 12000
    assert google["utilization_ratio"] == 1.0
    assert google["last_request_at"] == datetime(2026, 3, 11, 11, 59, tzinfo=UTC)
    assert custom["provider_label"] == "Custom"


@pytest.mark.asyncio
async def test_snapshot_uses_redis_when_available_and_record_redis_tolerates_failures():
    tracker = ProviderRequestUsageTracker()
    tracker._snapshot_from_redis = AsyncMock(return_value=[{"provider": "google"}])
    assert await tracker.snapshot() == [{"provider": "google"}]

    tracker = ProviderRequestUsageTracker()
    failing_client = _FakeRedisClient()
    failing_client.pipeline = lambda: _FakePipeline(should_raise=True)
    tracker._get_redis_client = AsyncMock(return_value=failing_client)
    assert await tracker._record_response_redis(provider="google", status_code=200, now=datetime.now(UTC)) is None
