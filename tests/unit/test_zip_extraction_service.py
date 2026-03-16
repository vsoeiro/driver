from __future__ import annotations

import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.application.drive import zip_extraction_service as zes


def _write_zip(target_path: str, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(target_path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


@pytest.mark.asyncio
async def test_extract_zip_creates_wrapper_uploads_files_and_deletes_source(monkeypatch):
    session = MagicMock()
    source_account = SimpleNamespace(id=uuid4())
    destination_account = SimpleNamespace(id=uuid4())
    session.get = AsyncMock(side_effect=[source_account, destination_account])

    source_item = SimpleNamespace(id="source-zip", name="bundle.zip", item_type="file")
    source_client = MagicMock()
    source_client.get_item_metadata = AsyncMock(return_value=source_item)
    source_client.delete_item = AsyncMock()

    async def download_to_path(_account, _item_id, target_path, timeout_seconds=None):  # noqa: ARG001
        _write_zip(
            target_path,
            {
                "covers/cover.jpg": b"cover-bytes",
                "book.cbz": b"book-bytes",
            },
        )
        return "bundle.zip"

    source_client.download_file_to_path = AsyncMock(side_effect=download_to_path)

    destination_client = MagicMock()
    destination_client.create_folder = AsyncMock(side_effect=[
        SimpleNamespace(id="wrapper-1", name="bundle", item_type="folder", size=0, mime_type=None, created_at=None, modified_at=None),
        SimpleNamespace(id="folder-1", name="covers", item_type="folder", size=0, mime_type=None, created_at=None, modified_at=None),
    ])
    destination_client.get_item_metadata = AsyncMock(side_effect=[
        SimpleNamespace(id="uploaded-1", name="cover.jpg", item_type="file", size=11, mime_type="image/jpeg", created_at=None, modified_at=None),
        SimpleNamespace(id="uploaded-2", name="book.cbz", item_type="file", size=10, mime_type="application/octet-stream", created_at=None, modified_at=None),
    ])

    monkeypatch.setattr(zes, "TokenManager", lambda db_session: SimpleNamespace(session=db_session))
    monkeypatch.setattr(
        zes,
        "build_drive_client",
        lambda account, token_manager: source_client if account is source_account else destination_client,  # noqa: ARG005
    )
    upsert_item_record_mock = AsyncMock()
    delete_item_and_descendants_mock = AsyncMock()
    enqueue_auto_mapping_jobs_mock = AsyncMock(return_value={
        "total_jobs": 2,
        "job_ids": ["job-a", "job-b"],
    })
    monkeypatch.setattr(zes, "upsert_item_record", upsert_item_record_mock)
    monkeypatch.setattr(zes, "delete_item_and_descendants", delete_item_and_descendants_mock)
    monkeypatch.setattr(zes, "enqueue_auto_mapping_jobs", enqueue_auto_mapping_jobs_mock)

    service = zes.ZipExtractionService(session)
    service.transfer_service.upload_local_file = AsyncMock(side_effect=["uploaded-1", "uploaded-2"])

    result = await service.extract_zip(
        source_account_id=source_account.id,
        source_item_id="source-zip",
        destination_account_id=destination_account.id,
        destination_folder_id="root",
        delete_source_after_extract=True,
    )

    assert result["total"] == 2
    assert result["success"] == 2
    assert result["failed"] == 0
    assert result["skipped"] == 0
    assert result["created_folders"] == 2
    assert result["wrapper_folder_id"] == "wrapper-1"
    assert result["wrapper_folder_name"] == "bundle"
    assert result["deleted_source"] is True
    assert result["auto_jobs_created"] == 2
    assert result["auto_job_ids"] == ["job-a", "job-b"]

    source_client.delete_item.assert_awaited_once_with(source_account, "source-zip")
    delete_item_and_descendants_mock.assert_awaited_once_with(
        session,
        account_id=source_account.id,
        item_id="source-zip",
    )
    enqueue_auto_mapping_jobs_mock.assert_awaited_once()
    assert service.transfer_service.upload_local_file.await_count == 2
    for await_call in service.transfer_service.upload_local_file.await_args_list:
        assert await_call.kwargs["conflict_behavior"] == "rename"
        assert await_call.kwargs["force_resumable"] is True

    latest_upserts = {}
    for await_call in upsert_item_record_mock.await_args_list:
        item_data = await_call.kwargs["item_data"]
        latest_upserts[item_data.id] = item_data
    assert latest_upserts["wrapper-1"].size == 21
    assert latest_upserts["folder-1"].size == 11


@pytest.mark.asyncio
async def test_extract_zip_strips_single_common_root_directory(monkeypatch):
    session = MagicMock()
    source_account = SimpleNamespace(id=uuid4())
    destination_account = SimpleNamespace(id=uuid4())
    session.get = AsyncMock(side_effect=[source_account, destination_account])

    source_item = SimpleNamespace(id="source-zip", name="bundle.zip", item_type="file")
    source_client = MagicMock()
    source_client.get_item_metadata = AsyncMock(return_value=source_item)

    async def download_to_path(_account, _item_id, target_path, timeout_seconds=None):  # noqa: ARG001
        _write_zip(
            target_path,
            {
                "inner/Book 01.cbz": b"book-1",
                "inner/Book 02.cbz": b"book-2",
            },
        )
        return "bundle.zip"

    source_client.download_file_to_path = AsyncMock(side_effect=download_to_path)

    destination_client = MagicMock()
    destination_client.create_folder = AsyncMock(return_value=SimpleNamespace(
        id="wrapper-1",
        name="bundle",
        item_type="folder",
        size=0,
        mime_type=None,
        created_at=None,
        modified_at=None,
    ))
    destination_client.get_item_metadata = AsyncMock(side_effect=[
        SimpleNamespace(id="uploaded-1", name="Book 01.cbz", item_type="file", size=6, mime_type="application/octet-stream", created_at=None, modified_at=None),
        SimpleNamespace(id="uploaded-2", name="Book 02.cbz", item_type="file", size=6, mime_type="application/octet-stream", created_at=None, modified_at=None),
    ])

    monkeypatch.setattr(zes, "TokenManager", lambda db_session: SimpleNamespace(session=db_session))
    monkeypatch.setattr(
        zes,
        "build_drive_client",
        lambda account, token_manager: source_client if account is source_account else destination_client,  # noqa: ARG005
    )
    upsert_item_record_mock = AsyncMock()
    monkeypatch.setattr(zes, "upsert_item_record", upsert_item_record_mock)
    monkeypatch.setattr(zes, "enqueue_auto_mapping_jobs", AsyncMock(return_value={}))

    service = zes.ZipExtractionService(session)
    service.transfer_service.upload_local_file = AsyncMock(side_effect=["uploaded-1", "uploaded-2"])

    result = await service.extract_zip(
        source_account_id=source_account.id,
        source_item_id="source-zip",
        destination_account_id=destination_account.id,
    )

    assert result["created_folders"] == 1
    destination_client.create_folder.assert_awaited_once()
    for await_call in service.transfer_service.upload_local_file.await_args_list:
        assert await_call.kwargs["folder_id"] == "wrapper-1"

    latest_upserts = {}
    for await_call in upsert_item_record_mock.await_args_list:
        item_data = await_call.kwargs["item_data"]
        latest_upserts[item_data.id] = item_data
    assert latest_upserts["wrapper-1"].size == 12


@pytest.mark.asyncio
async def test_extract_zip_keeps_source_when_members_fail_or_are_unsafe(monkeypatch):
    session = MagicMock()
    source_account = SimpleNamespace(id=uuid4())
    destination_account = SimpleNamespace(id=uuid4())
    session.get = AsyncMock(side_effect=[source_account, destination_account])

    source_item = SimpleNamespace(id="source-zip", name="bundle.zip", item_type="file")
    source_client = MagicMock()
    source_client.get_item_metadata = AsyncMock(return_value=source_item)
    source_client.delete_item = AsyncMock()

    async def download_to_path(_account, _item_id, target_path, timeout_seconds=None):  # noqa: ARG001
        _write_zip(
            target_path,
            {
                "good.txt": b"ok",
                "../evil.txt": b"bad",
            },
        )
        return "bundle.zip"

    source_client.download_file_to_path = AsyncMock(side_effect=download_to_path)

    destination_client = MagicMock()
    destination_client.create_folder = AsyncMock(return_value=SimpleNamespace(
        id="wrapper-1",
        name="bundle",
        item_type="folder",
        size=0,
        mime_type=None,
        created_at=None,
        modified_at=None,
    ))
    destination_client.get_item_metadata = AsyncMock()

    monkeypatch.setattr(zes, "TokenManager", lambda db_session: SimpleNamespace(session=db_session))
    monkeypatch.setattr(
        zes,
        "build_drive_client",
        lambda account, token_manager: source_client if account is source_account else destination_client,  # noqa: ARG005
    )
    upsert_item_record_mock = AsyncMock()
    delete_item_and_descendants_mock = AsyncMock()
    enqueue_auto_mapping_jobs_mock = AsyncMock()
    monkeypatch.setattr(zes, "upsert_item_record", upsert_item_record_mock)
    monkeypatch.setattr(zes, "delete_item_and_descendants", delete_item_and_descendants_mock)
    monkeypatch.setattr(zes, "enqueue_auto_mapping_jobs", enqueue_auto_mapping_jobs_mock)

    service = zes.ZipExtractionService(session)
    service.transfer_service.upload_local_file = AsyncMock(side_effect=RuntimeError("upload boom"))

    result = await service.extract_zip(
        source_account_id=source_account.id,
        source_item_id="source-zip",
        destination_account_id=destination_account.id,
        destination_folder_id="root",
        delete_source_after_extract=True,
    )

    assert result["total"] == 2
    assert result["success"] == 0
    assert result["failed"] == 1
    assert result["skipped"] == 1
    assert result["deleted_source"] is False
    assert len(result["error_items"]) == 2
    assert source_client.delete_item.await_count == 0
    assert delete_item_and_descendants_mock.await_count == 0
    assert enqueue_auto_mapping_jobs_mock.await_count == 0
    assert upsert_item_record_mock.await_count == 2
    latest_upserts = {}
    for await_call in upsert_item_record_mock.await_args_list:
        item_data = await_call.kwargs["item_data"]
        latest_upserts[item_data.id] = item_data
    assert latest_upserts["wrapper-1"].size == 0


def test_prepare_entries_rejects_password_protected_members():
    class _FakeInfo:
        filename = "secret.txt"
        flag_bits = 0x1

        def is_dir(self):
            return False

    archive = SimpleNamespace(infolist=lambda: [_FakeInfo()])

    with pytest.raises(ValueError, match="Password-protected ZIPs are not supported"):
        zes._prepare_entries(archive)


def test_normalize_member_path_rejects_zip_slip():
    parts, reason = zes._normalize_member_path("../secrets.txt")

    assert parts is None
    assert reason == "ZIP entry path is not safe for extraction"


def test_strip_common_root_directory_only_when_all_extractable_members_share_it():
    entries = [
        {"parts": ["inner", "one.cbz"], "skip_reason": None},
        {"parts": ["inner", "two.cbz"], "skip_reason": None},
        {"parts": None, "skip_reason": "unsafe"},
    ]

    zes._strip_common_root_directory(entries)

    assert entries[0]["parts"] == ["one.cbz"]
    assert entries[1]["parts"] == ["two.cbz"]
    assert entries[2]["parts"] is None
