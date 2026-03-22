from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.db.models import Job, JobAttempt
from backend.domain.errors import ValidationError
from backend.services.jobs import JobCancelledError, JobService
from backend.schemas.jobs import JobCreate


@pytest.mark.asyncio
async def test_delete_job_allows_finalized_status():
    session = AsyncMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="COMPLETED")
    session.get.return_value = job

    service = JobService(session)
    await service.delete_job(job_id)

    session.delete.assert_awaited_once_with(job)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_job_rejects_running_status():
    session = AsyncMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="RUNNING")
    session.get.return_value = job

    service = JobService(session)

    with pytest.raises(ValidationError):
        await service.delete_job(job_id)


@pytest.mark.asyncio
async def test_request_cancel_pending_job_marks_cancelled():
    session = AsyncMock()
    session.add = MagicMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="PENDING")
    session.get.return_value = job

    service = JobService(session)
    result = await service.request_cancel(job_id)

    assert result.status == "CANCELLED"
    assert result.result["cancelled"] is True
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_request_cancel_running_job_marks_cancelled():
    session = AsyncMock()
    session.add = MagicMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="RUNNING")
    session.get.return_value = job

    service = JobService(session)
    result = await service.request_cancel(job_id)

    assert result.status == "CANCELLED"
    assert result.result["cancelled"] is True
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_delete_job_allows_cancelled_status():
    session = AsyncMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="CANCELLED")
    session.get.return_value = job

    service = JobService(session)
    await service.delete_job(job_id)

    session.delete.assert_awaited_once_with(job)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_jobs_reads_without_reconciliation_write():
    session = AsyncMock()
    jobs_result = MagicMock()
    jobs_result.scalars.return_value.all.return_value = []
    session.execute.return_value = jobs_result

    service = JobService(session)
    jobs = await service.get_jobs()

    assert jobs == []
    assert session.execute.await_count == 1
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_jobs_filters_by_status():
    session = AsyncMock()
    jobs_result = MagicMock()
    jobs_result.scalars.return_value.all.return_value = []
    session.execute.return_value = jobs_result

    service = JobService(session)
    await service.get_jobs(statuses=["pending"])

    assert session.execute.await_count == 1
    jobs_stmt = session.execute.await_args_list[0].args[0]
    assert "jobs.status" in str(jobs_stmt).lower()


@pytest.mark.asyncio
async def test_avg_duration_uses_last_10_jobs_per_type():
    session = AsyncMock()
    now = datetime.now(UTC)
    rows = []
    for i in range(12):
        duration_seconds = 10 if i < 10 else 1000
        completed_at = now - timedelta(minutes=i)
        started_at = completed_at - timedelta(seconds=duration_seconds)
        rows.append(
            ("sync_items", started_at, completed_at)
        )
    result = MagicMock()
    result.all.return_value = rows
    session.execute.return_value = result

    service = JobService(session)
    avg_by_type, global_avg = await service._build_avg_duration_by_type()

    assert round(avg_by_type["sync_items"], 2) == 10.0
    assert round(global_avg, 2) == 10.0


@pytest.mark.asyncio
async def test_reprocess_job_clones_finalized_job():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    source_id = uuid4()
    new_id = uuid4()
    source = Job(
        id=source_id,
        type="sync_items",
        status="DEAD_LETTER",
        payload={"account_id": "acc-1"},
        max_retries=5,
    )
    session.get.return_value = source
    no_duplicate = MagicMock()
    no_duplicate.scalar_one_or_none.return_value = None
    session.execute.return_value = no_duplicate

    async def _refresh(job):
        if getattr(job, "id", None) is None:
            job.id = new_id

    session.refresh.side_effect = _refresh

    service = JobService(session, queue=queue)
    created = await service.reprocess_job(source_id)

    assert created.id == new_id
    assert created.reprocessed_from_job_id == source_id
    queue.enqueue_job.assert_awaited_once()
    args, kwargs = queue.enqueue_job.await_args
    assert args[0] == str(new_id)
    assert isinstance(kwargs.get("queue_name"), str)


@pytest.mark.asyncio
async def test_get_job_attempts_returns_rows():
    session = AsyncMock()
    service = JobService(session)
    job_id = uuid4()
    session.scalar.return_value = 1
    result = MagicMock()
    attempt = JobAttempt(id=uuid4(), job_id=job_id, attempt_number=1, status="COMPLETED", triggered_by="worker")
    result.scalars.return_value.all.return_value = [attempt]
    session.execute.return_value = result

    rows = await service.get_job_attempts(job_id, limit=5)

    assert len(rows) == 1
    assert rows[0].job_id == job_id


@pytest.mark.asyncio
async def test_update_job_progress_avoids_extra_status_read_on_success():
    session = AsyncMock()
    result = MagicMock()
    job = Job(id=uuid4(), type="sync_items", status="RUNNING")
    result.scalar_one_or_none.return_value = job
    session.execute.return_value = result

    service = JobService(session)
    updated = await service.update_job_progress(job.id, current=5, total=10)

    assert updated is job
    session.scalar.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_job_progress_raises_cancelled_when_job_was_cancelled():
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    session.scalar.return_value = "CANCELLED"
    job_id = uuid4()

    service = JobService(session)

    with pytest.raises(JobCancelledError):
        await service.update_job_progress(job_id, current=1, total=10)


def test_coerce_json_dict_and_normalize_job_fields_cover_legacy_values():
    job = Job(
        id=uuid4(),
        type="sync_items",
        status="COMPLETED",
        payload='{"account_id":"acc-1"}',
        result='{"ok":true}',
        metrics="not-json",
    )

    normalized = JobService._normalize_job_json_fields(JobService(AsyncMock()), job)

    assert JobService._coerce_json_dict(None, default_empty=False) is None
    assert JobService._coerce_json_dict("", default_empty=True) == {}
    assert JobService._coerce_json_dict('{"ok":true}', default_empty=False) == {"ok": True}
    assert normalized.payload == {"account_id": "acc-1"}
    assert normalized.result == {"ok": True}
    assert normalized.metrics is None


@pytest.mark.asyncio
async def test_recover_stale_running_jobs_cancels_jobs_and_open_attempts():
    session = AsyncMock()
    session.add = MagicMock()
    now = datetime.now(UTC)
    stale_job = Job(
        id=uuid4(),
        type="sync_items",
        status="RUNNING",
        started_at=now - timedelta(minutes=10),
        result='{"previous":"value"}',
    )
    open_attempt = JobAttempt(
        id=uuid4(),
        job_id=stale_job.id,
        attempt_number=1,
        status="RUNNING",
        started_at=now - timedelta(minutes=9),
        triggered_by="worker",
    )
    stale_result = MagicMock()
    stale_result.scalars.return_value.all.return_value = [stale_job]
    attempts_result = MagicMock()
    attempts_result.scalars.return_value.all.return_value = [open_attempt]
    session.execute.side_effect = [stale_result, attempts_result]

    service = JobService(session)
    service.settings = SimpleNamespace(worker_job_timeout_seconds=60)

    recovered = await service.recover_stale_running_jobs()

    assert recovered == 1
    assert stale_job.status == "CANCELLED"
    assert stale_job.result["stale_recovery"] is True
    assert stale_job.result["cancelled"] is True
    assert open_attempt.status == "CANCELLED"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_job_returns_active_duplicate_without_creating_new_job():
    session = AsyncMock()
    session.add = MagicMock()
    duplicate = Job(
        id=uuid4(),
        type="sync_items",
        status="PENDING",
        dedupe_key="dup-1",
        payload='{"account_id":"acc-1"}',
    )
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = duplicate
    session.execute.return_value = duplicate_result
    queue = AsyncMock()

    service = JobService(session, queue=queue)
    created = await service.create_job(
        JobCreate(type="sync_items", payload={"account_id": "acc-1"}, dedupe_key="dup-1")
    )

    assert created.id == duplicate.id
    assert created.payload == {"account_id": "acc-1"}
    session.add.assert_not_called()
    queue.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_job_and_start_job_enqueue_and_claim_pending_work():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    new_job_id = uuid4()
    session.scalar.return_value = 0
    no_duplicate = MagicMock()
    no_duplicate.scalar_one_or_none.return_value = None
    session.execute.return_value = no_duplicate

    async def _refresh(job):
        if getattr(job, "id", None) is None:
            job.id = new_job_id

    session.refresh.side_effect = _refresh

    service = JobService(session, queue=queue)
    created = await service.create_job(
        JobCreate(type="SYNC_ITEMS", payload={"account_id": "acc-1"})
    )

    assert created.id == new_job_id
    assert created.type == "sync_items"
    assert created.queue_dispatch_attempts == 1
    assert created.queue_enqueued_at is not None
    queue.enqueue_job.assert_awaited_once()

    pending_job = Job(id=new_job_id, type="sync_items", status="PENDING")
    session.get.return_value = pending_job
    started = await service.start_job(new_job_id)

    assert started.status == "RUNNING"
    assert getattr(started, "_claimed_by_worker") is True
    assert pending_job.started_at is not None
    assert session.commit.await_count >= 2


@pytest.mark.asyncio
async def test_create_job_records_dispatch_error_without_failing_job_creation():
    session = AsyncMock()
    session.add = MagicMock()
    no_duplicate = MagicMock()
    no_duplicate.scalar_one_or_none.return_value = None
    session.execute.return_value = no_duplicate
    queue = AsyncMock()
    queue.enqueue_job.side_effect = RuntimeError("redis down")
    new_job_id = uuid4()

    async def _refresh(job):
        if getattr(job, "id", None) is None:
            job.id = new_job_id

    session.refresh.side_effect = _refresh

    service = JobService(session, queue=queue)
    created = await service.create_job(JobCreate(type="sync_items", payload={"account_id": "acc-1"}))

    assert created.id == new_job_id
    assert created.status == "PENDING"
    assert created.queue_enqueued_at is None
    assert created.queue_dispatch_attempts == 1
    assert created.queue_last_error == "redis down"


@pytest.mark.asyncio
async def test_reconcile_pending_dispatches_retries_undispatched_jobs():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    job = Job(
        id=uuid4(),
        type="sync_items",
        status="PENDING",
        queue_name="driver:jobs:light",
        queue_dispatch_attempts=1,
        queue_enqueued_at=None,
    )
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [job]
    session.execute.return_value = rows

    service = JobService(session, queue=queue)
    reconciled = await service.reconcile_pending_dispatches(limit=10)

    assert reconciled == 1
    assert job.queue_dispatch_attempts == 2
    assert job.queue_enqueued_at is not None
    assert job.queue_last_error is None
    queue.enqueue_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_job_marks_existing_running_job_as_not_claimed():
    session = AsyncMock()
    running_job = Job(id=uuid4(), type="sync_items", status="RUNNING")
    session.get.return_value = running_job

    service = JobService(session)
    service.recover_stale_running_jobs = AsyncMock(return_value=0)
    started = await service.start_job(running_job.id)

    assert started.status == "RUNNING"
    assert getattr(started, "_claimed_by_worker") is False


@pytest.mark.asyncio
async def test_start_job_returns_existing_for_finalized_and_running_jobs():
    session = AsyncMock()
    completed_job = Job(
        id=uuid4(),
        type="sync_items",
        status="COMPLETED",
        payload='{"account_id":"acc-1"}',
        result='{"ok":true}',
    )
    session.get.return_value = completed_job

    service = JobService(session)
    service.recover_stale_running_jobs = AsyncMock(return_value=0)
    returned = await service.start_job(completed_job.id)

    assert returned.status == "COMPLETED"
    assert returned.payload == {"account_id": "acc-1"}
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_job_finishes_latest_attempt():
    session = AsyncMock()
    session.add = MagicMock()
    job_id = uuid4()
    job = Job(id=job_id, type="sync_items", status="RUNNING")
    attempt = JobAttempt(
        id=uuid4(),
        job_id=job_id,
        attempt_number=1,
        status="RUNNING",
        started_at=datetime.now(UTC) - timedelta(seconds=30),
        triggered_by="worker",
    )
    update_result = MagicMock()
    update_result.scalar_one.return_value = job
    attempt_result = MagicMock()
    attempt_result.scalar_one_or_none.return_value = attempt
    session.execute.side_effect = [update_result, attempt_result]

    service = JobService(session)
    completed = await service.complete_job(job_id, result={"ok": True})

    assert completed is job
    assert attempt.status == "COMPLETED"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_running_job_returns_existing_cancelled_job_without_update():
    session = AsyncMock()
    job_id = uuid4()
    cancelled_job = Job(id=job_id, type="sync_items", status="CANCELLED")
    session.scalar.return_value = "CANCELLED"
    session.get.return_value = cancelled_job

    service = JobService(session)
    returned = await service.cancel_running_job(job_id)

    assert returned is cancelled_job
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_fail_job_schedules_retry_and_reenqueues_work():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    job_id = uuid4()
    job = Job(
        id=job_id,
        type="sync_items",
        status="RUNNING",
        max_retries=3,
        retry_count=0,
    )
    attempt = JobAttempt(
        id=uuid4(),
        job_id=job_id,
        attempt_number=1,
        status="RUNNING",
        started_at=datetime.now(UTC) - timedelta(seconds=10),
        triggered_by="worker",
    )
    session.get.return_value = job
    attempt_result = MagicMock()
    attempt_result.scalar_one_or_none.return_value = attempt
    session.execute.return_value = attempt_result

    service = JobService(session, queue=queue)
    failed = await service.fail_job(job_id, "boom")

    assert failed.status == "RETRY_SCHEDULED"
    assert failed.result["retry_in_seconds"] == 2
    queue.enqueue_job.assert_awaited_once()
    assert attempt.status == "RETRY_SCHEDULED"


@pytest.mark.asyncio
async def test_fail_job_marks_dead_letter_when_retries_are_exhausted():
    session = AsyncMock()
    session.add = MagicMock()
    queue = AsyncMock()
    job_id = uuid4()
    job = Job(
        id=job_id,
        type="sync_items",
        status="RUNNING",
        max_retries=1,
        retry_count=1,
    )
    attempt = JobAttempt(
        id=uuid4(),
        job_id=job_id,
        attempt_number=2,
        status="RUNNING",
        started_at=datetime.now(UTC) - timedelta(seconds=10),
        triggered_by="worker",
    )
    session.get.return_value = job
    attempt_result = MagicMock()
    attempt_result.scalar_one_or_none.return_value = attempt
    session.execute.return_value = attempt_result

    service = JobService(session, queue=queue)
    failed = await service.fail_job(job_id, "still broken")

    assert failed.status == "DEAD_LETTER"
    assert failed.dead_letter_reason == "still broken"
    queue.enqueue_job.assert_not_awaited()
    assert attempt.status == "DEAD_LETTER"


@pytest.mark.asyncio
async def test_build_pending_job_estimates_accounts_for_running_slots_and_retry_delays():
    session = AsyncMock()
    now = datetime.now(UTC)
    pending_id = uuid4()
    retry_id = uuid4()
    running_result = MagicMock()
    running_result.all.return_value = [
        ("driver:jobs", "sync_items", now - timedelta(seconds=20), now - timedelta(seconds=21)),
    ]
    queued_result = MagicMock()
    queued_result.all.return_value = [
        (pending_id, "driver:jobs", "sync_items", "PENDING", None, now - timedelta(seconds=5)),
        (retry_id, "driver:jobs", "sync_items", "RETRY_SCHEDULED", now + timedelta(seconds=90), now - timedelta(seconds=4)),
    ]
    session.execute.side_effect = [running_result, queued_result]

    service = JobService(session)
    service.settings = SimpleNamespace(
        worker_concurrency=1,
        redis_queue_name="driver:jobs",
        job_queue_names={},
        job_type_queue_map={},
    )
    service._build_avg_duration_by_type = AsyncMock(return_value=({"sync_items": 60.0}, 60.0))

    estimates = await service._build_pending_job_estimates()

    assert estimates[pending_id]["queue_position"] == 1
    assert estimates[pending_id]["estimated_wait_seconds"] >= 40
    assert estimates[retry_id]["queue_position"] == 2
    assert estimates[retry_id]["estimated_wait_seconds"] >= 100
