"""Shared upload/move transfer logic used by routes and workers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from backend.common.upload_policy import DEFAULT_CHUNK_SIZE, is_large_upload
from backend.services.providers.base import DriveProviderClient


class DriveTransferService:
    """Provider-agnostic helpers for local-file uploads and cross-account copies."""

    async def upload_local_file(
        self,
        *,
        client: DriveProviderClient,
        account: Any,
        local_path: str,
        filename: str,
        folder_id: str = "root",
    ) -> str | None:
        """Upload a local file using small/resumable flow according to size policy."""
        file_size = os.path.getsize(local_path)
        with open(local_path, "rb") as handle:
            return await self._upload_file_handle(
                client=client,
                account=account,
                handle=handle,
                file_size=file_size,
                filename=filename,
                folder_id=folder_id,
            )

    async def upload_file_object(
        self,
        *,
        client: DriveProviderClient,
        account: Any,
        file_obj: BinaryIO,
        filename: str,
        folder_id: str = "root",
    ) -> str | None:
        """Upload a file-like object while keeping large uploads out of RAM."""
        safe_filename = Path(filename or "upload.bin").name
        current = file_obj.tell()
        file_obj.seek(0, 2)
        file_size = file_obj.tell()
        file_obj.seek(current)

        if is_large_upload(file_size):
            temp_dir = tempfile.mkdtemp(prefix="transfer_upload_")
            temp_path = str(Path(temp_dir) / safe_filename)
            try:
                with open(temp_path, "wb") as out:
                    while True:
                        chunk = file_obj.read(DEFAULT_CHUNK_SIZE)
                        if not chunk:
                            break
                        out.write(chunk)
                return await self.upload_local_file(
                    client=client,
                    account=account,
                    local_path=temp_path,
                    filename=safe_filename,
                    folder_id=folder_id,
                )
            finally:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    Path(temp_dir).rmdir()
                except Exception:
                    pass

        file_obj.seek(current)
        uploaded = await client.upload_small_file(account, safe_filename, file_obj.read(), folder_id)
        return uploaded.id

    async def transfer_file_between_accounts(
        self,
        *,
        source_client: DriveProviderClient,
        destination_client: DriveProviderClient,
        source_account: Any,
        destination_account: Any,
        source_item_id: str,
        source_item_name: str,
        destination_folder_id: str = "root",
    ) -> str | None:
        """Stream file through disk temp storage to avoid loading large files in memory."""
        temp_dir = tempfile.mkdtemp(prefix="transfer_copy_")
        filename = Path(source_item_name or source_item_id).name
        temp_path = str(Path(temp_dir) / filename)
        try:
            downloaded_name = await source_client.download_file_to_path(
                source_account,
                source_item_id,
                temp_path,
            )
            upload_name = downloaded_name or filename
            uploaded_item_id = await self.upload_local_file(
                client=destination_client,
                account=destination_account,
                local_path=temp_path,
                filename=upload_name,
                folder_id=destination_folder_id,
            )
            await source_client.delete_item(source_account, source_item_id)
            return uploaded_item_id
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass
            try:
                Path(temp_dir).rmdir()
            except Exception:
                pass

    async def _upload_file_handle(
        self,
        *,
        client: DriveProviderClient,
        account: Any,
        handle: BinaryIO,
        file_size: int,
        filename: str,
        folder_id: str,
    ) -> str | None:
        if not is_large_upload(file_size):
            uploaded = await client.upload_small_file(account, filename, handle.read(), folder_id)
            return uploaded.id

        session_data = await client.create_upload_session(account, filename, folder_id)
        upload_url = session_data["upload_url"]
        uploaded_item_id: str | None = None
        offset = 0
        while offset < file_size:
            chunk = handle.read(DEFAULT_CHUNK_SIZE)
            if not chunk:
                break

            end = offset + len(chunk) - 1
            upload_result = await client.upload_chunk(
                upload_url,
                chunk,
                offset,
                end,
                file_size,
            )
            if isinstance(upload_result, dict) and upload_result.get("id"):
                uploaded_item_id = str(upload_result["id"])
            offset += len(chunk)
        return uploaded_item_id
