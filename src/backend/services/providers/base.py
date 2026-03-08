"""Provider-agnostic drive client contract."""

from __future__ import annotations

from typing import Any, Protocol

from backend.db.models import LinkedAccount
from backend.schemas.drive import DriveItem, DriveListResponse


class DriveProviderClient(Protocol):
    """Common contract for drive providers (Microsoft, Google, etc.)."""

    async def get_user_info(self, account: LinkedAccount) -> dict: ...
    async def list_root_items(self, account: LinkedAccount) -> DriveListResponse: ...
    async def list_folder_items(self, account: LinkedAccount, item_id: str) -> DriveListResponse: ...
    async def list_items_by_next_link(self, account: LinkedAccount, next_link: str) -> DriveListResponse: ...
    async def get_item_metadata(self, account: LinkedAccount, item_id: str) -> DriveItem: ...
    async def get_download_url(self, account: LinkedAccount, item_id: str) -> str: ...
    async def download_file_bytes(
        self,
        account: LinkedAccount,
        item_id: str,
        timeout_seconds: float | None = None,
    ) -> tuple[str, bytes]: ...
    async def download_file_to_path(
        self,
        account: LinkedAccount,
        item_id: str,
        target_path: str,
        timeout_seconds: float | None = None,
    ) -> str: ...
    async def search_items(self, account: LinkedAccount, query: str) -> DriveListResponse: ...
    async def get_quota(self, account: LinkedAccount) -> dict: ...
    async def get_item_path(self, account: LinkedAccount, item_id: str) -> list[dict]: ...
    async def get_recent_items(self, account: LinkedAccount) -> DriveListResponse: ...
    async def get_shared_with_me(self, account: LinkedAccount) -> DriveListResponse: ...
    async def upload_small_file(
        self,
        account: LinkedAccount,
        filename: str,
        content: bytes | Any,
        folder_id: str = "root",
    ) -> DriveItem: ...
    async def create_upload_session(
        self,
        account: LinkedAccount,
        filename: str,
        folder_id: str = "root",
        conflict_behavior: str = "rename",
    ) -> dict: ...
    async def upload_chunk(
        self,
        upload_url: str,
        chunk: bytes,
        start_byte: int,
        end_byte: int,
        total_size: int,
        *,
        account: LinkedAccount | None = None,
    ) -> dict: ...
    async def create_folder(
        self,
        account: LinkedAccount,
        name: str,
        parent_id: str = "root",
        conflict_behavior: str = "rename",
    ) -> DriveItem: ...
    async def update_item(
        self,
        account: LinkedAccount,
        item_id: str,
        name: str | None = None,
        parent_id: str | None = None,
    ) -> DriveItem: ...
    async def delete_item(self, account: LinkedAccount, item_id: str) -> None: ...
    async def batch_delete_items(self, account: LinkedAccount, item_ids: list[str]) -> None: ...
    async def copy_item(
        self,
        account: LinkedAccount,
        item_id: str,
        name: str | None = None,
        parent_id: str = "root",
    ) -> str: ...
