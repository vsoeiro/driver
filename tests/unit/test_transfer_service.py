from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.application.drive.transfer_service import DriveTransferService
from backend.common.upload_policy import DEFAULT_CHUNK_SIZE, MAX_SIMPLE_UPLOAD_SIZE


@pytest.mark.asyncio
async def test_upload_local_file_uses_small_upload_for_small_files():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "small.bin"
        path.write_bytes(b"abc")

        client = MagicMock()
        client.upload_small_file = AsyncMock(return_value=SimpleNamespace(id="small-1"))
        client.create_upload_session = AsyncMock()
        client.upload_chunk = AsyncMock()
        account = SimpleNamespace(id="acc-1")

        service = DriveTransferService()
        uploaded_id = await service.upload_local_file(
            client=client,
            account=account,
            local_path=str(path),
            filename="small.bin",
            folder_id="root",
        )

        assert uploaded_id == "small-1"
        client.upload_small_file.assert_awaited_once()
        client.create_upload_session.assert_not_awaited()
        client.upload_chunk.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_local_file_uses_chunked_upload_for_large_files():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "large.bin"
        path.write_bytes(b"x" * (MAX_SIMPLE_UPLOAD_SIZE + 100))

        client = MagicMock()
        client.upload_small_file = AsyncMock()
        client.create_upload_session = AsyncMock(return_value={"upload_url": "https://upload.example"})
        client.upload_chunk = AsyncMock(side_effect=[{}, {"id": "large-1"}])
        account = SimpleNamespace(id="acc-1")

        service = DriveTransferService()
        uploaded_id = await service.upload_local_file(
            client=client,
            account=account,
            local_path=str(path),
            filename="large.bin",
            folder_id="root",
        )

        assert uploaded_id == "large-1"
        client.upload_small_file.assert_not_awaited()
        client.create_upload_session.assert_awaited_once()
        assert client.upload_chunk.await_count >= 2


@pytest.mark.asyncio
async def test_upload_local_file_respects_provider_next_expected_ranges():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "large.bin"
        path.write_bytes(b"x" * (MAX_SIMPLE_UPLOAD_SIZE + 100))

        client = MagicMock()
        client.upload_small_file = AsyncMock()
        client.create_upload_session = AsyncMock(return_value={"upload_url": "https://upload.example"})
        client.upload_chunk = AsyncMock(
            side_effect=[
                {"next_expected_ranges": ["1048576-"]},
                {},
                {"id": "large-1"},
            ]
        )
        account = SimpleNamespace(id="acc-1")

        service = DriveTransferService()
        uploaded_id = await service.upload_local_file(
            client=client,
            account=account,
            local_path=str(path),
            filename="large.bin",
            folder_id="root",
        )

        assert uploaded_id == "large-1"
        first_call = client.upload_chunk.await_args_list[0]
        second_call = client.upload_chunk.await_args_list[1]
        third_call = client.upload_chunk.await_args_list[2]
        assert first_call.args[2] == 0
        assert first_call.args[3] == DEFAULT_CHUNK_SIZE - 1
        assert second_call.args[2] == 1048576
        assert third_call.args[2] == 1048576 + DEFAULT_CHUNK_SIZE


@pytest.mark.asyncio
async def test_transfer_file_between_accounts_streams_via_temp_file():
    source_client = MagicMock()
    destination_client = MagicMock()
    source_account = SimpleNamespace(id="source-acc")
    destination_account = SimpleNamespace(id="dest-acc")

    async def _download_to_path(_account, _item_id, target_path: str, timeout_seconds=None):  # noqa: ARG001
        Path(target_path).write_bytes(b"hello")
        return "comic.cbz"

    source_client.download_file_to_path = AsyncMock(side_effect=_download_to_path)
    source_client.delete_item = AsyncMock()
    destination_client.upload_small_file = AsyncMock(return_value=SimpleNamespace(id="new-item-id"))
    destination_client.create_upload_session = AsyncMock()
    destination_client.upload_chunk = AsyncMock()

    service = DriveTransferService()
    moved_id = await service.transfer_file_between_accounts(
        source_client=source_client,
        destination_client=destination_client,
        source_account=source_account,
        destination_account=destination_account,
        source_item_id="item-1",
        source_item_name="comic.cbz",
        destination_folder_id="root",
    )

    assert moved_id == "new-item-id"
    source_client.download_file_to_path.assert_awaited_once()
    source_client.delete_item.assert_awaited_once_with(source_account, "item-1")
