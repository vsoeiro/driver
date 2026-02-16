from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.services.cron_utils import seconds_until_next_run
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
