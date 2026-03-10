"""Dropbox API client."""

from __future__ import annotations

import logging
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from backend.core.exceptions import DriveOrganizerError
from backend.db.models import LinkedAccount
from backend.schemas.drive import DriveItem, DriveListResponse
from backend.security.token_manager import TokenManager
from backend.services.providers.http_base import OAuthHTTPClientBase
from backend.services.provider_request_usage import provider_request_usage_tracker

logger = logging.getLogger(__name__)

DROPBOX_API_BASE_URL = "https://api.dropboxapi.com/2"
DROPBOX_CONTENT_BASE_URL = "https://content.dropboxapi.com/2"
DROPBOX_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DROPBOX_UPLOAD_SESSION_TTL = timedelta(hours=4)
_DROPBOX_UPLOAD_SESSIONS: dict[str, dict[str, Any]] = {}


def _extract_session_key(upload_url: str) -> str:
    if not upload_url.startswith("dropbox-session://"):
        raise DriveOrganizerError("Invalid Dropbox upload session URL", status_code=400)
    key = upload_url.split("dropbox-session://", 1)[1].strip()
    if not key:
        raise DriveOrganizerError("Invalid Dropbox upload session URL", status_code=400)
    return key


def _prune_expired_sessions() -> None:
    now = datetime.now(UTC)
    stale_keys = [
        key
        for key, payload in _DROPBOX_UPLOAD_SESSIONS.items()
        if not isinstance(payload, dict)
        or not isinstance(payload.get("expires_at"), datetime)
        or payload["expires_at"] <= now
    ]
    for key in stale_keys:
        _DROPBOX_UPLOAD_SESSIONS.pop(key, None)


def _session_payload_to_url(payload: dict[str, Any]) -> tuple[str, datetime]:
    _prune_expired_sessions()
    expires_at = datetime.now(UTC) + DROPBOX_UPLOAD_SESSION_TTL
    key = uuid4().hex
    _DROPBOX_UPLOAD_SESSIONS[key] = {**payload, "expires_at": expires_at}
    return f"dropbox-session://{key}", expires_at


def _session_payload_from_url(upload_url: str) -> dict[str, Any]:
    _prune_expired_sessions()
    key = _extract_session_key(upload_url)
    payload = _DROPBOX_UPLOAD_SESSIONS.get(key)
    if not isinstance(payload, dict):
        raise DriveOrganizerError("Invalid or expired Dropbox upload session", status_code=400)
    return payload


def _clear_session_payload(upload_url: str) -> None:
    try:
        key = _extract_session_key(upload_url)
    except DriveOrganizerError:
        return
    _DROPBOX_UPLOAD_SESSIONS.pop(key, None)


class DropboxDriveClient(OAuthHTTPClientBase):
    """Async client for Dropbox API."""

    def __init__(self, token_manager: TokenManager) -> None:
        super().__init__(token_manager)

    async def _request_rpc(
        self,
        endpoint: str,
        account: LinkedAccount,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{DROPBOX_API_BASE_URL}{endpoint}"

        response = await self._perform_oauth_request(
            method="POST",
            url=url,
            account=account,
            timeout=DROPBOX_TIMEOUT,
            request_headers={"Content-Type": "application/json"},
            timeout_error_factory=lambda exc: DriveOrganizerError(
                "Dropbox request timed out. Please try again.",
                status_code=504,
            ),
            connection_error_factory=lambda exc: DriveOrganizerError(
                "Failed to reach Dropbox. Please try again.",
                status_code=502,
            ),
            json=payload or {},
        )

        if response.status_code >= 400:
            msg = self.parse_error_message(response, default=response.text or "Dropbox request failed")
            raise DriveOrganizerError(f"Dropbox API error: {msg}", status_code=response.status_code)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def _request_content_download(
        self,
        endpoint: str,
        account: LinkedAccount,
        *,
        payload: dict[str, Any],
        timeout: httpx.Timeout | None = None,
    ) -> tuple[dict[str, Any], bytes]:
        url = f"{DROPBOX_CONTENT_BASE_URL}{endpoint}"
        response = await self._perform_oauth_request(
            method="POST",
            url=url,
            account=account,
            timeout=timeout or DROPBOX_TIMEOUT,
            request_headers={
                "Dropbox-API-Arg": json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
            },
            timeout_error_factory=lambda exc: DriveOrganizerError(
                "Dropbox download timed out. Please try again.",
                status_code=504,
            ),
            connection_error_factory=lambda exc: DriveOrganizerError(
                "Failed to reach Dropbox. Please try again.",
                status_code=502,
            ),
            content=b"",
        )
        if response.status_code >= 400:
            msg = self.parse_error_message(response, default=response.text or "Dropbox request failed")
            raise DriveOrganizerError(f"Dropbox API error: {msg}", status_code=response.status_code)
        metadata_raw = response.headers.get("Dropbox-API-Result", "{}")
        try:
            metadata = json.loads(metadata_raw)
        except Exception:
            metadata = {}
        return metadata, response.content

    async def _request_content_upload(
        self,
        endpoint: str,
        account: LinkedAccount,
        *,
        arg_payload: dict[str, Any],
        content: bytes,
    ) -> dict[str, Any]:
        url = f"{DROPBOX_CONTENT_BASE_URL}{endpoint}"
        response = await self._perform_oauth_request(
            method="POST",
            url=url,
            account=account,
            timeout=DROPBOX_TIMEOUT,
            request_headers={
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": json.dumps(arg_payload, separators=(",", ":"), ensure_ascii=True),
            },
            timeout_error_factory=lambda exc: DriveOrganizerError(
                "Dropbox upload timed out. Please try again.",
                status_code=504,
            ),
            connection_error_factory=lambda exc: DriveOrganizerError(
                "Failed to reach Dropbox. Please try again.",
                status_code=502,
            ),
            content=content,
        )
        if response.status_code >= 400:
            msg = self.parse_error_message(response, default=response.text or "Dropbox request failed")
            raise DriveOrganizerError(f"Dropbox API error: {msg}", status_code=response.status_code)
        return response.json() if response.content else {}

    @staticmethod
    def _normalize_path(path: str) -> str:
        value = (path or "").strip()
        if not value or value == "/":
            return ""
        return value if value.startswith("/") else f"/{value}"

    async def _resolve_folder_path(self, account: LinkedAccount, folder_id: str) -> str:
        normalized = (folder_id or "").strip()
        if not normalized or normalized == "root":
            return ""
        metadata = await self._request_rpc(
            "/files/get_metadata",
            account,
            payload={
                "path": normalized if normalized.startswith("id:") else normalized,
                "include_deleted": False,
            },
        )
        if metadata.get(".tag") != "folder":
            raise DriveOrganizerError("Target parent is not a folder", status_code=400)
        return self._normalize_path(metadata.get("path_display") or metadata.get("path_lower") or "")

    @staticmethod
    def _parse_single_item(item: dict[str, Any]) -> DriveItem:
        item_type = item.get(".tag", "file")
        is_folder = item_type == "folder"
        try:
            size = int(item.get("size", 0))
        except Exception:
            size = 0
        if is_folder:
            size = 0
        return DriveItem(
            id=item.get("id", ""),
            name=item.get("name", ""),
            item_type="folder" if is_folder else "file",
            size=size,
            mime_type=(None if is_folder else item.get("content_hash")),
            child_count=None,
            created_at=item.get("client_modified"),
            modified_at=item.get("server_modified"),
            web_url=None,
            download_url=None,
        )

    @staticmethod
    def _parse_list(data: dict[str, Any], folder_path: str = "/") -> DriveListResponse:
        entries = data.get("entries", []) if isinstance(data, dict) else []
        items = [DropboxDriveClient._parse_single_item(entry) for entry in entries]
        cursor = data.get("cursor")
        has_more = bool(data.get("has_more"))
        next_link = f"dropbox:cursor:{cursor}" if cursor and has_more else None
        return DriveListResponse(items=items, folder_path=folder_path, next_link=next_link)

    async def get_user_info(self, account: LinkedAccount) -> dict:
        return await self._request_rpc("/users/get_current_account", account, payload={})

    async def list_root_items(self, account: LinkedAccount, page_size: int = 50) -> DriveListResponse:
        data = await self._request_rpc(
            "/files/list_folder",
            account,
            payload={
                "path": "",
                "recursive": False,
                "include_deleted": False,
                "include_non_downloadable_files": True,
                "limit": max(1, min(200, int(page_size))),
            },
        )
        return self._parse_list(data, "/")

    async def list_folder_items(self, account: LinkedAccount, item_id: str, page_size: int = 50) -> DriveListResponse:
        folder_path = await self._resolve_folder_path(account, item_id)
        data = await self._request_rpc(
            "/files/list_folder",
            account,
            payload={
                "path": folder_path,
                "recursive": False,
                "include_deleted": False,
                "include_non_downloadable_files": True,
                "limit": max(1, min(200, int(page_size))),
            },
        )
        return self._parse_list(data, folder_path or "/")

    async def list_items_by_next_link(self, account: LinkedAccount, next_link: str) -> DriveListResponse:
        if not next_link.startswith("dropbox:cursor:"):
            raise DriveOrganizerError("Invalid Dropbox pagination cursor", status_code=400)
        cursor = next_link.split("dropbox:cursor:", 1)[1]
        data = await self._request_rpc(
            "/files/list_folder/continue",
            account,
            payload={"cursor": cursor},
        )
        return self._parse_list(data, "/")

    async def get_item_metadata(self, account: LinkedAccount, item_id: str) -> DriveItem:
        data = await self._request_rpc(
            "/files/get_metadata",
            account,
            payload={"path": item_id if item_id.startswith("id:") else item_id},
        )
        return self._parse_single_item(data)

    async def get_download_url(self, account: LinkedAccount, item_id: str) -> str:
        data = await self._request_rpc(
            "/files/get_temporary_link",
            account,
            payload={"path": item_id if item_id.startswith("id:") else item_id},
        )
        link = data.get("link")
        if not link:
            raise DriveOrganizerError("Dropbox did not return a temporary link", status_code=502)
        return str(link)

    async def download_file_bytes(
        self,
        account: LinkedAccount,
        item_id: str,
        timeout_seconds: float | None = None,
    ) -> tuple[str, bytes]:
        timeout = httpx.Timeout(timeout_seconds, connect=10.0) if timeout_seconds else DROPBOX_TIMEOUT
        metadata, content = await self._request_content_download(
            "/files/download",
            account,
            payload={"path": item_id if item_id.startswith("id:") else item_id},
            timeout=timeout,
        )
        if metadata.get(".tag") == "folder":
            raise DriveOrganizerError("Cannot download a folder as a file", status_code=400)
        filename = metadata.get("name") or "file"
        return str(filename), content

    async def download_file_to_path(
        self,
        account: LinkedAccount,
        item_id: str,
        target_path: str,
        timeout_seconds: float | None = None,
    ) -> str:
        filename, content = await self.download_file_bytes(
            account,
            item_id,
            timeout_seconds=timeout_seconds,
        )
        output_path = Path(target_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
        return filename

    async def search_items(self, account: LinkedAccount, query: str) -> DriveListResponse:
        data = await self._request_rpc(
            "/files/search_v2",
            account,
            payload={
                "query": query,
                "options": {
                    "path": "",
                    "max_results": 200,
                    "filename_only": False,
                },
            },
        )
        matches = data.get("matches", [])
        entries = []
        for match in matches:
            metadata = (
                (match.get("metadata") or {}).get("metadata")
                if isinstance(match, dict)
                else None
            )
            if isinstance(metadata, dict):
                entries.append(metadata)
        return DriveListResponse(items=[self._parse_single_item(entry) for entry in entries], folder_path="/")

    async def get_quota(self, account: LinkedAccount) -> dict:
        data = await self._request_rpc("/users/get_space_usage", account, payload={})
        used = int(data.get("used", 0))
        allocation = data.get("allocation", {}) if isinstance(data, dict) else {}
        total = 0
        if allocation.get(".tag") == "individual":
            total = int((allocation.get("allocated") or 0))
        elif allocation.get(".tag") == "team":
            total = int((allocation.get("allocated") or 0))
        remaining = max(0, total - used) if total else 0
        return {"total": total, "used": used, "remaining": remaining, "state": "normal"}

    async def get_item_path(self, account: LinkedAccount, item_id: str) -> list[dict]:
        if item_id == "root":
            return []
        metadata = await self._request_rpc(
            "/files/get_metadata",
            account,
            payload={"path": item_id if item_id.startswith("id:") else item_id},
        )
        path_display = metadata.get("path_display") or ""
        if not path_display:
            return []

        parts = [part for part in path_display.split("/") if part]
        if not parts:
            return []

        breadcrumb: list[dict] = []
        current_path = ""
        for name in parts:
            current_path = f"{current_path}/{name}"
            try:
                part_meta = await self._request_rpc(
                    "/files/get_metadata",
                    account,
                    payload={"path": current_path},
                )
                part_id = part_meta.get("id") or current_path
            except Exception:
                part_id = current_path
            breadcrumb.append({"id": part_id, "name": name})
        return breadcrumb

    async def get_recent_items(self, account: LinkedAccount) -> DriveListResponse:
        data = await self._request_rpc(
            "/files/list_folder",
            account,
            payload={
                "path": "",
                "recursive": True,
                "include_deleted": False,
                "include_non_downloadable_files": True,
                "limit": 200,
            },
        )
        items = [self._parse_single_item(entry) for entry in data.get("entries", [])]
        items.sort(key=lambda item: item.modified_at or "", reverse=True)
        return DriveListResponse(items=items[:100], folder_path="/")

    async def get_shared_with_me(self, account: LinkedAccount) -> DriveListResponse:
        data = await self._request_rpc("/sharing/list_received_files", account, payload={"limit": 200})
        entries = data.get("entries", [])
        items: list[DriveItem] = []
        for entry in entries:
            file_data = entry.get("file_metadata") if isinstance(entry, dict) else None
            if isinstance(file_data, dict):
                items.append(self._parse_single_item(file_data))
        return DriveListResponse(items=items, folder_path="/shared-with-me")

    async def upload_small_file(
        self,
        account: LinkedAccount,
        filename: str,
        content: bytes | Any,
        folder_id: str = "root",
    ) -> DriveItem:
        folder_path = await self._resolve_folder_path(account, folder_id)
        raw = content if isinstance(content, bytes) else content.read()
        file_path = f"{folder_path}/{filename}" if folder_path else f"/{filename}"
        data = await self._request_content_upload(
            "/files/upload",
            account,
            arg_payload={
                "path": file_path,
                "mode": "add",
                "autorename": True,
                "mute": False,
                "strict_conflict": False,
            },
            content=raw,
        )
        return self._parse_single_item(data)

    async def create_upload_session(
        self,
        account: LinkedAccount,
        filename: str,
        folder_id: str = "root",
        conflict_behavior: str = "rename",
    ) -> dict:
        folder_path = await self._resolve_folder_path(account, folder_id)
        commit_path = f"{folder_path}/{filename}" if folder_path else f"/{filename}"
        data = await self._request_rpc("/files/upload_session/start", account, payload={"close": False})
        session_id = data.get("session_id")
        if not session_id:
            raise DriveOrganizerError("Dropbox did not return upload session id", status_code=502)

        payload = {
            "provider": "dropbox",
            "session_id": session_id,
            "commit_path": commit_path,
            "autorename": conflict_behavior != "fail",
            "account_id": str(account.id),
        }
        upload_url, expires_at = _session_payload_to_url(payload)
        return {
            "upload_url": upload_url,
            "expiration": expires_at,
        }

    async def upload_chunk(
        self,
        upload_url: str,
        chunk: bytes,
        start_byte: int,
        end_byte: int,
        total_size: int,
        *,
        account: LinkedAccount | None = None,
    ) -> dict:
        payload = _session_payload_from_url(upload_url)
        if payload.get("provider") != "dropbox":
            raise DriveOrganizerError("Invalid Dropbox upload session payload", status_code=400)
        session_id = payload.get("session_id")
        commit_path = payload.get("commit_path")
        session_account_id = str(payload.get("account_id") or "").strip()
        if not session_id or not commit_path or not session_account_id:
            raise DriveOrganizerError("Invalid Dropbox upload session payload", status_code=400)
        if account is None or str(account.id) != session_account_id:
            raise DriveOrganizerError("Upload session does not match account", status_code=403)

        access_token = await self._token_manager.get_valid_access_token(account)
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/octet-stream"}
        client = await self._get_http_client(timeout=DROPBOX_TIMEOUT)
        cursor = {"session_id": session_id, "offset": start_byte}

        try:
            if end_byte + 1 >= total_size:
                response = await client.post(
                    f"{DROPBOX_CONTENT_BASE_URL}/files/upload_session/finish",
                    headers={
                        **headers,
                        "Dropbox-API-Arg": json.dumps(
                            {
                                "cursor": cursor,
                                "commit": {
                                    "path": commit_path,
                                    "mode": "add",
                                    "autorename": bool(payload.get("autorename", True)),
                                    "mute": False,
                                    "strict_conflict": False,
                                },
                            },
                            separators=(",", ":"),
                            ensure_ascii=True,
                        ),
                    },
                    content=chunk,
                    timeout=DROPBOX_TIMEOUT,
                )
            else:
                response = await client.post(
                    f"{DROPBOX_CONTENT_BASE_URL}/files/upload_session/append_v2",
                    headers={
                        **headers,
                        "Dropbox-API-Arg": json.dumps(
                            {"cursor": cursor, "close": False},
                            separators=(",", ":"),
                            ensure_ascii=True,
                        ),
                    },
                    content=chunk,
                    timeout=DROPBOX_TIMEOUT,
                )
            await provider_request_usage_tracker.record_response(provider="dropbox", status_code=response.status_code)
        except httpx.TimeoutException as exc:
            await provider_request_usage_tracker.record_transport_error(provider="dropbox", kind="timeout")
            raise DriveOrganizerError("Dropbox chunk upload timed out", status_code=504) from exc
        except httpx.HTTPError as exc:
            await provider_request_usage_tracker.record_transport_error(provider="dropbox", kind="connection")
            raise DriveOrganizerError("Failed to upload chunk to Dropbox", status_code=502) from exc

        if response.status_code >= 400:
            message = self.parse_error_message(response, default=response.text or "Dropbox chunk upload failed")
            raise DriveOrganizerError(f"Dropbox chunk upload failed: {message}", status_code=response.status_code)

        if response.status_code == 200 and response.content:
            _clear_session_payload(upload_url)
            return response.json()
        return {"next_expected_ranges": [f"{end_byte + 1}-"]}

    async def create_folder(
        self,
        account: LinkedAccount,
        name: str,
        parent_id: str = "root",
        conflict_behavior: str = "rename",
    ) -> DriveItem:
        parent_path = await self._resolve_folder_path(account, parent_id)
        target_path = f"{parent_path}/{name}" if parent_path else f"/{name}"
        data = await self._request_rpc(
            "/files/create_folder_v2",
            account,
            payload={"path": target_path, "autorename": conflict_behavior != "fail"},
        )
        metadata = data.get("metadata", {})
        return self._parse_single_item(metadata)

    async def update_item(
        self,
        account: LinkedAccount,
        item_id: str,
        name: str | None = None,
        parent_id: str | None = None,
    ) -> DriveItem:
        current = await self._request_rpc(
            "/files/get_metadata",
            account,
            payload={"path": item_id if item_id.startswith("id:") else item_id},
        )
        current_path = self._normalize_path(current.get("path_display") or current.get("path_lower") or "")
        if not current_path:
            raise DriveOrganizerError("Unable to resolve current Dropbox item path", status_code=400)

        target_name = name or current.get("name") or ""
        if not target_name:
            raise DriveOrganizerError("Invalid target item name", status_code=400)

        if parent_id:
            parent_path = await self._resolve_folder_path(account, parent_id)
            target_path = f"{parent_path}/{target_name}" if parent_path else f"/{target_name}"
        else:
            parent_path = "/".join(current_path.split("/")[:-1])
            target_path = f"{parent_path}/{target_name}" if parent_path else f"/{target_name}"

        if target_path == current_path:
            return self._parse_single_item(current)

        moved = await self._request_rpc(
            "/files/move_v2",
            account,
            payload={
                "from_path": current_path,
                "to_path": target_path,
                "autorename": True,
                "allow_shared_folder": True,
                "allow_ownership_transfer": False,
            },
        )
        metadata = moved.get("metadata", {})
        return self._parse_single_item(metadata)

    async def delete_item(self, account: LinkedAccount, item_id: str) -> None:
        await self._request_rpc(
            "/files/delete_v2",
            account,
            payload={"path": item_id if item_id.startswith("id:") else item_id},
        )

    async def batch_delete_items(self, account: LinkedAccount, item_ids: list[str]) -> None:
        if not item_ids:
            return
        data = await self._request_rpc(
            "/files/delete_batch",
            account,
            payload={"entries": [{"path": item_id} for item_id in item_ids]},
        )
        tag = (data or {}).get(".tag")
        if tag != "async_job_id":
            return

        async_job_id = data.get("async_job_id")
        for _ in range(20):
            status_data = await self._request_rpc(
                "/files/delete_batch/check",
                account,
                payload={"async_job_id": async_job_id},
            )
            status_tag = (status_data or {}).get(".tag")
            if status_tag == "complete":
                return
            if status_tag == "failed":
                raise DriveOrganizerError("Dropbox batch delete failed", status_code=502)

    async def copy_item(
        self,
        account: LinkedAccount,
        item_id: str,
        name: str | None = None,
        parent_id: str = "root",
    ) -> str:
        current = await self._request_rpc(
            "/files/get_metadata",
            account,
            payload={"path": item_id if item_id.startswith("id:") else item_id},
        )
        source_path = self._normalize_path(current.get("path_display") or current.get("path_lower") or "")
        if not source_path:
            raise DriveOrganizerError("Unable to resolve source path for copy", status_code=400)
        target_name = name or current.get("name") or "copy"
        parent_path = await self._resolve_folder_path(account, parent_id)
        to_path = f"{parent_path}/{target_name}" if parent_path else f"/{target_name}"

        await self._request_rpc(
            "/files/copy_v2",
            account,
            payload={
                "from_path": source_path,
                "to_path": to_path,
                "autorename": True,
                "allow_shared_folder": True,
                "allow_ownership_transfer": False,
            },
        )
        return f"dropbox://copy-complete/{to_path}"


async def close_dropbox_drive_http_client() -> None:
    """Close shared Dropbox HTTP client used across request scopes."""
    await DropboxDriveClient.close_http_client()
