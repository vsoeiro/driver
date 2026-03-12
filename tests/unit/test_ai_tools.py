from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.core.exceptions import DriveOrganizerError
from backend.services.ai import tools


def test_parse_optional_uuid():
    value = uuid4()
    assert tools._parse_optional_uuid(str(value)) == value
    assert tools._parse_optional_uuid("") is None
    assert tools._parse_optional_uuid("not-a-uuid") is None


@pytest.mark.asyncio
async def test_resolve_read_account_uuid_variants():
    account = SimpleNamespace(
        id=uuid4(),
        provider="microsoft",
        email="reader@example.com",
        display_name="Reader",
        provider_account_id="reader-acc",
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [account])))
    )

    assert await tools._resolve_read_account_uuid(session, str(account.id)) == account.id
    assert await tools._resolve_read_account_uuid(session, "reader@example.com") == account.id
    assert await tools._resolve_read_account_uuid(session, "microsoft") == account.id


@pytest.mark.asyncio
async def test_resolve_read_account_uuid_rejects_ambiguous_and_missing():
    account_a = SimpleNamespace(
        id=uuid4(),
        provider="microsoft",
        email="shared@example.com",
        display_name="Shared A",
        provider_account_id="acc-a",
    )
    account_b = SimpleNamespace(
        id=uuid4(),
        provider="microsoft",
        email="other.shared@example.com",
        display_name="Shared B",
        provider_account_id="acc-b",
    )
    ambiguous = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [account_a, account_b])))
    )
    missing = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])))
    )

    with pytest.raises(DriveOrganizerError) as ambiguous_exc:
        await tools._resolve_read_account_uuid(ambiguous, "microsoft")
    assert "Conta ambigua" in str(ambiguous_exc.value)

    with pytest.raises(DriveOrganizerError) as missing_exc:
        await tools._resolve_read_account_uuid(missing, "google")
    assert "Conta nao encontrada" in str(missing_exc.value)


@pytest.mark.asyncio
async def test_tool_accounts_list_and_resolve():
    accounts = [
        SimpleNamespace(id=uuid4(), provider="microsoft", email="reader@example.com", display_name="Reader", is_active=True, created_at=1, provider_account_id="reader"),
        SimpleNamespace(id=uuid4(), provider="google", email="drive@example.com", display_name="Drive", is_active=False, created_at=2, provider_account_id="drive"),
    ]
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: accounts)))
    )

    listed = await tools._tool_accounts_list(session, {})
    resolved = await tools._tool_accounts_resolve(session, {"query": "drive@example.com"})

    assert listed["accounts"][0]["email"] == "reader@example.com"
    assert resolved["total_matches"] == 1
    assert resolved["accounts"][0]["provider"] == "google"


@pytest.mark.asyncio
async def test_tool_jobs_create_sync_and_catalog(monkeypatch):
    job = SimpleNamespace(id=uuid4(), status="queued", type="sync_items")
    enqueue = AsyncMock(return_value=job)
    monkeypatch.setattr(tools, "enqueue_job_command", enqueue)

    result = await tools._tool_jobs_create_sync(SimpleNamespace(), {"account_id": "acc-1"})
    registry = tools.build_tool_registry()
    catalog = tools.catalog_entries(registry)

    assert result == {"job_id": str(job.id), "status": "queued", "type": "sync_items"}
    assert any(entry["name"] == "accounts.list" for entry in catalog)
    enqueue.assert_awaited_once_with(
        SimpleNamespace(),
        job_type="sync_items",
        payload={"account_id": "acc-1"},
    )
