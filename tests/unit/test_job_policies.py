from types import SimpleNamespace

from backend.domain.jobs.policies import (
    build_default_dedupe_key,
    resolve_job_dedupe_key,
    resolve_job_max_retries,
    resolve_job_queue_alias,
)
from backend.domain.jobs.types import JobType


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        job_type_queue_map={"sync_items": "priority_sync"},
        job_type_max_retries_map={"sync_items": 7},
        job_default_max_retries=3,
    )


def test_resolve_job_queue_alias_prefers_requested_value_then_policy():
    settings = _settings()
    assert resolve_job_queue_alias("sync_items", settings, "manual_queue") == "manual_queue"
    assert resolve_job_queue_alias("sync_items", settings, None) == "priority_sync"
    assert resolve_job_queue_alias("unknown_type", settings, None) == "default"


def test_default_policy_for_image_analysis_jobs():
    settings = _settings()
    assert resolve_job_queue_alias(JobType.ANALYZE_IMAGE_ASSETS.value, settings, None) == "vision"
    dedupe = build_default_dedupe_key(
        JobType.ANALYZE_IMAGE_ASSETS,
        {"account_id": "a1", "item_ids": ["1", "2"], "reprocess": False},
    )
    assert dedupe is not None
    assert dedupe.startswith("analyze_image_assets:")


def test_resolve_job_max_retries_uses_requested_policy_and_default():
    settings = _settings()
    assert resolve_job_max_retries("sync_items", settings, 2) == 2
    assert resolve_job_max_retries("sync_items", settings, None) == 7
    assert resolve_job_max_retries("unknown_type", settings, None) == 3


def test_resolve_job_dedupe_key_is_stable_and_can_be_overridden():
    payload = {"account_id": "acc-1", "ignored": "x"}
    generated = build_default_dedupe_key(JobType.SYNC_ITEMS, payload)
    assert generated is not None
    assert generated.startswith("sync_items:")

    regenerated = build_default_dedupe_key(JobType.SYNC_ITEMS, {"ignored": "x", "account_id": "acc-1"})
    assert generated == regenerated

    explicit = resolve_job_dedupe_key(
        job_type=JobType.SYNC_ITEMS,
        payload=payload,
        requested_dedupe_key="  custom-key  ",
    )
    assert explicit == "custom-key"
