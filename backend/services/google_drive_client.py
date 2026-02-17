"""Google Drive API client."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from backend.core.exceptions import DriveOrganizerError
from backend.db.models import LinkedAccount
from backend.schemas.drive import DriveItem, DriveListResponse
from backend.services.token_manager import TokenManager

logger = logging.getLogger(__name__)

GOOGLE_DRIVE_BASE_URL = "https://www.googleapis.com/drive/v3"
GOOGLE_UPLOAD_BASE_URL = "https://www.googleapis.com/upload/drive/v3"
GOOGLE_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"

FILE_FIELDS = (
    "id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents"
)


class GoogleDriveClient:
    """Async client for Google Drive API."""

    def __init__(self, token_manager: TokenManager) -> None:
        self._token_manager = token_manager

    async def _request(
        self,
        method: str,
        endpoint: str,
        account: LinkedAccount,
        *,
        use_upload_api: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        base = GOOGLE_UPLOAD_BASE_URL if use_upload_api else GOOGLE_DRIVE_BASE_URL
        url = endpoint if endpoint.startswith("http") else f"{base}{endpoint}"

        request_headers = kwargs.pop("headers", {})

        async def _send_request(access_token: str) -> httpx.Response:
            headers = dict(request_headers)
            headers["Authorization"] = f"Bearer {access_token}"
            async with httpx.AsyncClient(timeout=GOOGLE_TIMEOUT) as client:
                return await client.request(method=method, url=url, headers=headers, **kwargs)

        try:
            access_token = await self._token_manager.get_valid_access_token(account)
            response = await _send_request(access_token)
            if response.status_code == 401:
                logger.warning(
                    "Google Drive returned 401 for account %s; forcing token refresh and retrying once.",
                    account.id,
                )
                access_token = await self._token_manager.force_refresh_access_token(account)
                response = await _send_request(access_token)
        except httpx.TimeoutException as exc:
            raise DriveOrganizerError(
                "Google Drive request timed out. Please try again.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise DriveOrganizerError(
                "Failed to reach Google Drive. Please try again.",
                status_code=502,
            ) from exc

        if response.status_code >= 400 and response.status_code != 308:
            msg = response.text
            try:
                data = response.json()
                msg = data.get("error", {}).get("message", msg)
            except Exception:
                pass
            raise DriveOrganizerError(f"Google Drive API error: {msg}", status_code=response.status_code)

        return response

    def _parse_single_item(self, item: dict) -> DriveItem:
        is_folder = item.get("mimeType") == GOOGLE_FOLDER_MIME
        raw_size = item.get("size", 0)
        quota_size = item.get("quotaBytesUsed", 0)
        size = quota_size if is_folder and quota_size not in (None, "") else raw_size
        try:
            size = int(size)
        except Exception:
            size = 0

        return DriveItem(
            id=item["id"],
            name=item.get("name", ""),
            item_type="folder" if is_folder else "file",
            size=size,
            mime_type=None if is_folder else item.get("mimeType"),
            child_count=None,
            created_at=item.get("createdTime"),
            modified_at=item.get("modifiedTime"),
            web_url=item.get("webViewLink"),
            download_url=item.get("webContentLink"),
        )

    def _parse_list(self, data: dict, folder_path: str) -> DriveListResponse:
        items = [self._parse_single_item(file_data) for file_data in data.get("files", [])]
        return DriveListResponse(
            items=items,
            folder_path=folder_path,
            next_link=data.get("nextPageToken"),
        )

    async def get_user_info(self, account: LinkedAccount) -> dict:
        response = await self._request(
            "GET",
            "/about",
            account,
            params={"fields": "user"},
        )
        return response.json().get("user", {})

    async def list_root_items(self, account: LinkedAccount) -> DriveListResponse:
        response = await self._request(
            "GET",
            "/files",
            account,
            params={
                "q": "'root' in parents and trashed=false",
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "pageSize": 200,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        return self._parse_list(response.json(), "/")

    async def list_folder_items(self, account: LinkedAccount, item_id: str) -> DriveListResponse:
        response = await self._request(
            "GET",
            "/files",
            account,
            params={
                "q": f"'{item_id}' in parents and trashed=false",
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "pageSize": 200,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        return self._parse_list(response.json(), item_id)

    async def list_items_by_next_link(self, account: LinkedAccount, next_link: str) -> DriveListResponse:
        if next_link.startswith("http"):
            response = await self._request("GET", next_link, account)
        else:
            response = await self._request(
                "GET",
                "/files",
                account,
                params={
                    "q": "trashed=false",
                    "fields": f"nextPageToken,files({FILE_FIELDS})",
                    "pageToken": next_link,
                    "pageSize": 200,
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                },
            )
        return self._parse_list(response.json(), "/")

    async def get_item_metadata(self, account: LinkedAccount, item_id: str) -> DriveItem:
        response = await self._request(
            "GET",
            f"/files/{item_id}",
            account,
            params={
                "fields": FILE_FIELDS,
                "supportsAllDrives": "true",
            },
        )
        return self._parse_single_item(response.json())

    async def get_download_url(self, account: LinkedAccount, item_id: str) -> str:
        response = await self._request(
            "GET",
            f"/files/{item_id}",
            account,
            params={
                "fields": "id,name,mimeType,webContentLink",
                "supportsAllDrives": "true",
            },
        )
        data = response.json()
        if data.get("mimeType", "").startswith("application/vnd.google-apps."):
            raise DriveOrganizerError("Google Docs native files do not provide direct download URL", status_code=400)

        download_url = data.get("webContentLink")
        if not download_url:
            raise DriveOrganizerError("Download URL not available for this item", status_code=404)
        return download_url

    async def download_file_bytes(self, account: LinkedAccount, item_id: str) -> tuple[str, bytes]:
        metadata_response = await self._request(
            "GET",
            f"/files/{item_id}",
            account,
            params={"fields": "id,name,mimeType", "supportsAllDrives": "true"},
        )
        metadata = metadata_response.json()
        mime_type = metadata.get("mimeType", "")
        if mime_type.startswith("application/vnd.google-apps."):
            raise DriveOrganizerError("Downloading Google Docs native files is not supported yet", status_code=400)

        file_response = await self._request(
            "GET",
            f"/files/{item_id}",
            account,
            params={"alt": "media", "supportsAllDrives": "true"},
        )
        return metadata.get("name", "file"), file_response.content

    async def download_file_to_path(self, account: LinkedAccount, item_id: str, target_path: str) -> str:
        filename, content = await self.download_file_bytes(account, item_id)
        with open(target_path, "wb") as f:
            f.write(content)
        return filename

    async def search_items(self, account: LinkedAccount, query: str) -> DriveListResponse:
        escaped = query.replace("\\", "\\\\").replace("'", "\\'")
        response = await self._request(
            "GET",
            "/files",
            account,
            params={
                "q": f"name contains '{escaped}' and trashed=false",
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "pageSize": 100,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        return self._parse_list(response.json(), f"search:{query}")

    async def get_quota(self, account: LinkedAccount) -> dict:
        response = await self._request(
            "GET",
            "/about",
            account,
            params={"fields": "storageQuota"},
        )
        quota = response.json().get("storageQuota", {})
        total = int(quota.get("limit") or 0)
        used = int(quota.get("usage") or 0)
        remaining = max(total - used, 0) if total else 0
        return {
            "total": total,
            "used": used,
            "remaining": remaining,
            "state": "normal",
        }

    async def get_item_path(self, account: LinkedAccount, item_id: str) -> list[dict]:
        if item_id == "root":
            return [{"id": "root", "name": "Root"}]

        breadcrumb: list[dict] = []
        current_id = item_id
        max_depth = 64

        while current_id and max_depth > 0:
            response = await self._request(
                "GET",
                f"/files/{current_id}",
                account,
                params={"fields": "id,name,parents", "supportsAllDrives": "true"},
            )
            data = response.json()
            breadcrumb.insert(0, {"id": data["id"], "name": data.get("name", "")})
            parents = data.get("parents") or []
            if not parents:
                breadcrumb.insert(0, {"id": "root", "name": "Root"})
                break

            parent_id = parents[0]
            if parent_id == "root":
                breadcrumb.insert(0, {"id": "root", "name": "Root"})
                break
            current_id = parent_id
            max_depth -= 1

        return breadcrumb

    async def get_recent_items(self, account: LinkedAccount) -> DriveListResponse:
        response = await self._request(
            "GET",
            "/files",
            account,
            params={
                "q": "trashed=false",
                "orderBy": "viewedByMeTime desc",
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "pageSize": 100,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        return self._parse_list(response.json(), "recent")

    async def get_shared_with_me(self, account: LinkedAccount) -> DriveListResponse:
        response = await self._request(
            "GET",
            "/files",
            account,
            params={
                "q": "sharedWithMe = true and trashed=false",
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "pageSize": 100,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        return self._parse_list(response.json(), "shared")

    async def upload_small_file(
        self,
        account: LinkedAccount,
        filename: str,
        content: bytes | Any,
        folder_id: str = "root",
    ) -> DriveItem:
        if hasattr(content, "read"):
            content = content.read()
        if not isinstance(content, (bytes, bytearray)):
            raise DriveOrganizerError("Invalid upload content", status_code=400)

        metadata: dict[str, Any] = {"name": filename}
        if folder_id:
            metadata["parents"] = [folder_id]

        boundary = "----drive-organizer-google-upload"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + bytes(content) + f"\r\n--{boundary}--".encode("utf-8")

        response = await self._request(
            "POST",
            "/files",
            account,
            use_upload_api=True,
            params={"uploadType": "multipart", "fields": FILE_FIELDS, "supportsAllDrives": "true"},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            content=body,
        )
        return self._parse_single_item(response.json())

    async def create_upload_session(
        self,
        account: LinkedAccount,
        filename: str,
        folder_id: str = "root",
        conflict_behavior: str = "rename",
    ) -> dict:
        metadata: dict[str, Any] = {"name": filename}
        if folder_id:
            metadata["parents"] = [folder_id]

        response = await self._request(
            "POST",
            "/files",
            account,
            use_upload_api=True,
            params={"uploadType": "resumable", "supportsAllDrives": "true"},
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/octet-stream",
            },
            json=metadata,
        )
        upload_url = response.headers.get("Location")
        if not upload_url:
            raise DriveOrganizerError("Upload session URL was not returned by Google Drive", status_code=502)

        return {
            "upload_url": upload_url,
            "expiration": datetime.now(UTC) + timedelta(days=1),
        }

    async def upload_chunk(
        self,
        upload_url: str,
        chunk: bytes,
        start_byte: int,
        end_byte: int,
        total_size: int,
    ) -> dict:
        async with httpx.AsyncClient(timeout=GOOGLE_TIMEOUT) as client:
            response = await client.put(
                upload_url,
                content=chunk,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{total_size}",
                },
            )

        if response.status_code == 308:
            range_header = response.headers.get("Range")
            if range_header and "-" in range_header:
                last_byte = int(range_header.split("-")[-1])
                return {"next_expected_ranges": [f"{last_byte + 1}-"]}
            return {"next_expected_ranges": [f"{end_byte + 1}-"]}

        if response.status_code >= 400:
            raise DriveOrganizerError(
                f"Google Drive chunk upload failed: {response.text}",
                status_code=response.status_code,
            )

        return response.json() if response.content else {}

    async def create_folder(
        self,
        account: LinkedAccount,
        name: str,
        parent_id: str = "root",
        conflict_behavior: str = "rename",
    ) -> DriveItem:
        body = {
            "name": name,
            "mimeType": GOOGLE_FOLDER_MIME,
            "parents": [parent_id],
        }
        response = await self._request(
            "POST",
            "/files",
            account,
            params={"fields": FILE_FIELDS, "supportsAllDrives": "true"},
            json=body,
        )
        return self._parse_single_item(response.json())

    async def update_item(
        self,
        account: LinkedAccount,
        item_id: str,
        name: str | None = None,
        parent_id: str | None = None,
    ) -> DriveItem:
        body: dict[str, Any] = {}
        params: dict[str, Any] = {
            "fields": FILE_FIELDS,
            "supportsAllDrives": "true",
        }

        if name:
            body["name"] = name

        if parent_id:
            current_meta = await self._request(
                "GET",
                f"/files/{item_id}",
                account,
                params={"fields": "parents", "supportsAllDrives": "true"},
            )
            current_parents = current_meta.json().get("parents") or []
            params["addParents"] = parent_id
            if current_parents:
                params["removeParents"] = ",".join([pid for pid in current_parents if pid != parent_id])

        if not body and "addParents" not in params:
            return await self.get_item_metadata(account, item_id)

        response = await self._request(
            "PATCH",
            f"/files/{item_id}",
            account,
            params=params,
            json=body if body else None,
        )
        return self._parse_single_item(response.json())

    async def delete_item(self, account: LinkedAccount, item_id: str) -> None:
        await self._request(
            "DELETE",
            f"/files/{item_id}",
            account,
            params={"supportsAllDrives": "true"},
        )

    async def batch_delete_items(self, account: LinkedAccount, item_ids: list[str]) -> None:
        semaphore = asyncio.Semaphore(5)

        async def _delete_one(iid: str) -> None:
            async with semaphore:
                try:
                    await self.delete_item(account, iid)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to delete item %s on Google Drive: %s", iid, exc)

        await asyncio.gather(*[_delete_one(item_id) for item_id in item_ids])

    async def copy_item(
        self,
        account: LinkedAccount,
        item_id: str,
        name: str | None = None,
        parent_id: str = "root",
    ) -> str:
        body: dict[str, Any] = {"parents": [parent_id]}
        if name:
            body["name"] = name

        response = await self._request(
            "POST",
            f"/files/{item_id}/copy",
            account,
            params={"fields": "id,webViewLink", "supportsAllDrives": "true"},
            json=body,
        )
        data = response.json()
        return data.get("webViewLink") or data.get("id", "")
