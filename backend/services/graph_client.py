"""Microsoft Graph API client.

This module provides an async client for interacting with Microsoft Graph API
to access OneDrive files and user information.
"""

import logging
from typing import Any

import httpx

from backend.core.exceptions import GraphAPIError
from backend.db.models import LinkedAccount
from backend.schemas.drive import DriveItem, DriveListResponse
from backend.services.token_manager import TokenManager

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class GraphClient:
    """Async client for Microsoft Graph API.

    Provides methods to access OneDrive files and user information.
    """

    def __init__(self, token_manager: TokenManager) -> None:
        """Initialize the Graph client.

        Parameters
        ----------
        token_manager : TokenManager
            Token manager for obtaining valid access tokens.
        """
        self._token_manager = token_manager

    async def _request(
        self,
        method: str,
        endpoint: str,
        account: LinkedAccount,
        **kwargs: Any,
    ) -> dict:
        """Make an authenticated request to Graph API.

        Parameters
        ----------
        method : str
            HTTP method.
        endpoint : str
            API endpoint path.
        account : LinkedAccount
            Account to use for authentication.
        **kwargs : Any
            Additional arguments for httpx.

        Returns
        -------
        dict
            JSON response from the API.

        Raises
        ------
        GraphAPIError
            If the API request fails.
        """
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            url = f"{GRAPH_BASE_URL}{endpoint}"

        async def _send_request(access_token: str) -> httpx.Response:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT) as client:
                return await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    **kwargs,
                )

        try:
            access_token = await self._token_manager.get_valid_access_token(account)
            response = await _send_request(access_token)
            if response.status_code == 401:
                logger.warning(
                    "Graph returned 401 for account %s; forcing token refresh and retrying once.",
                    account.id,
                )
                access_token = await self._token_manager.force_refresh_access_token(account)
                response = await _send_request(access_token)
        except httpx.TimeoutException as exc:
            logger.error("Graph API timeout: %s %s", method, endpoint)
            raise GraphAPIError(
                "Microsoft Graph request timed out. Please try again.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("Graph API connection error: %s %s - %s", method, endpoint, exc)
            raise GraphAPIError(
                "Failed to reach Microsoft Graph. Please try again.",
                status_code=502,
            ) from exc

        if response.status_code >= 400:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("error", {}).get("message", response.text)
            logger.error("Graph API error: %s - %s", response.status_code, error_msg)
            raise GraphAPIError(error_msg, status_code=response.status_code)

        if response.status_code == 204 or not response.content:
            return {}

        return response.json()

    async def get_user_info(self, account: LinkedAccount) -> dict:
        """Get the authenticated user's profile information.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.

        Returns
        -------
        dict
            User profile information.
        """
        return await self._request("GET", "/me", account)

    async def list_root_items(self, account: LinkedAccount) -> DriveListResponse:
        """List items in the root of OneDrive.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.

        Returns
        -------
        DriveListResponse
            List of items in the root folder.
        """
        data = await self._request("GET", "/me/drive/root/children", account)
        return self._parse_drive_items(data, "/")

    async def list_folder_items(
        self,
        account: LinkedAccount,
        item_id: str,
    ) -> DriveListResponse:
        """List items in a specific folder.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            The folder item ID.

        Returns
        -------
        DriveListResponse
            List of items in the folder.
        """
        data = await self._request(
            "GET",
            f"/me/drive/items/{item_id}/children",
            account,
        )
        return self._parse_drive_items(data, item_id)

    async def list_items_by_next_link(
        self,
        account: LinkedAccount,
        next_link: str,
    ) -> DriveListResponse:
        """Fetch next page of items using Graph pagination link."""
        data = await self._request("GET", next_link, account)
        return self._parse_drive_items(data, "/")

    async def get_item_metadata(
        self,
        account: LinkedAccount,
        item_id: str,
    ) -> DriveItem:
        """Get metadata for a specific item.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            The item ID.

        Returns
        -------
        DriveItem
            Item metadata.
        """
        data = await self._request("GET", f"/me/drive/items/{item_id}", account)
        return self._parse_single_item(data)

    async def get_download_url(
        self,
        account: LinkedAccount,
        item_id: str,
    ) -> str:
        """Get a temporary download URL for a file.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            The file item ID.

        Returns
        -------
        str
            Temporary download URL.

        Raises
        ------
        GraphAPIError
            If the item is not a file or download URL is unavailable.
        """
        data = await self._request("GET", f"/me/drive/items/{item_id}", account)

        download_url = data.get("@microsoft.graph.downloadUrl")
        if not download_url:
            raise GraphAPIError("Download URL not available for this item")

        return download_url

    async def download_file_bytes(
        self,
        account: LinkedAccount,
        item_id: str,
    ) -> tuple[str, bytes]:
        """Download raw bytes for a file item.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            The file item ID.

        Returns
        -------
        tuple[str, bytes]
            Tuple with (filename, file bytes).

        Raises
        ------
        GraphAPIError
            If the item is a folder or download fails.
        """
        item_data = await self._request("GET", f"/me/drive/items/{item_id}", account)

        if "folder" in item_data:
            raise GraphAPIError("Cannot download a folder as a file", status_code=400)

        download_url = item_data.get("@microsoft.graph.downloadUrl")
        if not download_url:
            raise GraphAPIError("Download URL not available for this item")

        filename = item_data.get("name", "file")

        try:
            async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT) as client:
                response = await client.get(download_url)
        except httpx.TimeoutException as exc:
            raise GraphAPIError(
                f"Timed out downloading file {filename}",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise GraphAPIError(
                f"Failed to download file {filename}",
                status_code=502,
            ) from exc

        if response.status_code >= 400:
            error_msg = response.text or "Download failed"
            raise GraphAPIError(error_msg, status_code=response.status_code)

        return filename, response.content

    async def download_file_to_path(
        self,
        account: LinkedAccount,
        item_id: str,
        target_path: str,
    ) -> str:
        """Download a file directly to a local path (streaming).

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            The file item ID.
        target_path : str
            Local path to save the file to.

        Returns
        -------
        str
            The filename of the downloaded file.
        """
        item_data = await self._request("GET", f"/me/drive/items/{item_id}", account)

        if "folder" in item_data:
            raise GraphAPIError("Cannot download a folder as a file", status_code=400)

        download_url = item_data.get("@microsoft.graph.downloadUrl")
        if not download_url:
            raise GraphAPIError("Download URL not available for this item")

        filename = item_data.get("name", "file")

        try:
            async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT) as client:
                async with client.stream("GET", download_url) as response:
                    if response.status_code >= 400:
                         await response.read() # Read error
                         raise GraphAPIError(f"Download failed: {response.status_code}", status_code=response.status_code)
                    
                    with open(target_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            
        except httpx.TimeoutException as exc:
            raise GraphAPIError(
                f"Timed out downloading file {filename}",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise GraphAPIError(
                f"Failed to download file {filename}",
                status_code=502,
            ) from exc

        return filename

    def _parse_drive_items(self, data: dict, folder_path: str) -> DriveListResponse:
        """Parse Graph API response into DriveListResponse.

        Parameters
        ----------
        data : dict
            Raw API response.
        folder_path : str
            Current folder path.

        Returns
        -------
        DriveListResponse
            Parsed response.
        """
        items = [self._parse_single_item(item) for item in data.get("value", [])]

        return DriveListResponse(
            items=items,
            folder_path=folder_path,
            next_link=data.get("@odata.nextLink"),
        )

    def _parse_single_item(self, item: dict) -> DriveItem:
        """Parse a single item from Graph API.

        Parameters
        ----------
        item : dict
            Raw item data.

        Returns
        -------
        DriveItem
            Parsed item.
        """
        is_folder = "folder" in item
        item_type = "folder" if is_folder else "file"

        return DriveItem(
            id=item["id"],
            name=item["name"],
            item_type=item_type,
            size=item.get("size", 0),
            mime_type=item.get("file", {}).get("mimeType") if not is_folder else None,
            child_count=item.get("folder", {}).get("childCount") if is_folder else None,
            created_at=item.get("createdDateTime"),
            modified_at=item.get("lastModifiedDateTime"),
            web_url=item.get("webUrl"),
            download_url=item.get("@microsoft.graph.downloadUrl"),
        )

    async def search_items(
        self,
        account: LinkedAccount,
        query: str,
    ) -> DriveListResponse:
        """Search for items in OneDrive.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        query : str
            Search query string.

        Returns
        -------
        DriveListResponse
            List of matching items.
        """
        from urllib.parse import quote

        encoded_query = quote(query)
        data = await self._request(
            "GET",
            f"/me/drive/root/search(q='{encoded_query}')",
            account,
        )
        return self._parse_drive_items(data, f"search:{query}")

    async def get_quota(self, account: LinkedAccount) -> dict:
        """Get OneDrive storage quota information.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.

        Returns
        -------
        dict
            Quota information with total, used, remaining, and state.
        """
        data = await self._request("GET", "/me/drive", account)
        quota = data.get("quota", {})

        return {
            "total": quota.get("total", 0),
            "used": quota.get("used", 0),
            "remaining": quota.get("remaining", 0),
            "state": quota.get("state", "normal"),
        }

    async def get_item_path(
        self,
        account: LinkedAccount,
        item_id: str,
    ) -> list[dict]:
        """Get the full path (breadcrumb) for an item.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            The item ID.

        Returns
        -------
        list[dict]
            List of path components from root to item.
        """
        breadcrumb = []
        current_id = item_id
        
        # Safety limit for depth
        max_depth = 50

        while max_depth > 0:
            try:
                data = await self._request(
                    "GET",
                    f"/me/drive/items/{current_id}?$select=id,name,parentReference,root",
                    account,
                )
            except Exception as e:
                logger.warning(f"Failed to fetch breadcrumb item {current_id}: {e}")
                break

            # Prepend the current item
            breadcrumb.insert(0, {"id": data["id"], "name": data.get("name")})

            # Check if we reached the root
            if "root" in data:
                break
            
            # Get parent ID to continue traversal
            parent_ref = data.get("parentReference", {})
            parent_id = parent_ref.get("id")
            
            if not parent_id:
                break
                
            current_id = parent_id
            max_depth -= 1

        return breadcrumb

    async def get_recent_items(self, account: LinkedAccount) -> DriveListResponse:
        """Get recently accessed items.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.

        Returns
        -------
        DriveListResponse
            List of recent items.
        """
        data = await self._request("GET", "/me/drive/recent", account)
        return self._parse_drive_items(data, "recent")

    async def get_shared_with_me(self, account: LinkedAccount) -> DriveListResponse:
        """Get items shared with the current user.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.

        Returns
        -------
        DriveListResponse
            List of shared items.
        """
        data = await self._request("GET", "/me/drive/sharedWithMe", account)
        return self._parse_drive_items(data, "shared")

    async def upload_small_file(
        self,
        account: LinkedAccount,
        filename: str,
        content: bytes | Any,  # Any for file-like object
        folder_id: str = "root",
    ) -> DriveItem:
        """Upload a small file (< 4MB) directly.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        filename : str
            Name of the file to create.
        content : bytes | file-like
            File content or file-like object.
        folder_id : str, optional
            Target folder ID. Defaults to 'root'.

        Returns
        -------
        DriveItem
            The created file item.
        """
        access_token = await self._token_manager.get_valid_access_token(account)

        if folder_id == "root":
            endpoint = f"/me/drive/root:/{filename}:/content"
        else:
            endpoint = f"/me/drive/items/{folder_id}:/{filename}:/content"

        url = f"{GRAPH_BASE_URL}{endpoint}"
        
        # httpx handles bytes, iterables, or file-like objects in 'content'
        # If it's a file-like object from FastAPI (SpooledTemporaryFile), keep it as is.
        # However, AsyncClient requires async iterator for streams, or bytes.
        
        request_content = content
        if hasattr(content, "read"):
             # It's a file-like object. Wrap it in an async generator.
             async def file_iterator():
                 chunk_size = 64 * 1024
                 while True:
                     data = content.read(chunk_size)
                     if not data:
                         break
                     yield data
             request_content = file_iterator()
        
        async with httpx.AsyncClient() as client:
            response = await client.put(
                url,
                content=request_content,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/octet-stream",
                },
            )

        if response.status_code >= 400:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("error", {}).get("message", response.text)
            raise GraphAPIError(error_msg, status_code=response.status_code)

        return self._parse_single_item(response.json())

    async def create_upload_session(
        self,
        account: LinkedAccount,
        filename: str,
        folder_id: str = "root",
        conflict_behavior: str = "rename",
    ) -> dict:
        """Create an upload session for large files.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        filename : str
            Name of the file to create.
        folder_id : str, optional
            Target folder ID. Defaults to 'root'.
        conflict_behavior : str, optional
            What to do if file exists. Defaults to 'rename'.

        Returns
        -------
        dict
            Upload session info with uploadUrl and expiration.
        """
        if folder_id == "root":
            endpoint = f"/me/drive/root:/{filename}:/createUploadSession"
        else:
            endpoint = f"/me/drive/items/{folder_id}:/{filename}:/createUploadSession"

        body = {
            "item": {
                "@microsoft.graph.conflictBehavior": conflict_behavior,
                "name": filename,
            }
        }

        data = await self._request("POST", endpoint, account, json=body)

        return {
            "upload_url": data.get("uploadUrl"),
            "expiration": data.get("expirationDateTime"),
        }

    async def upload_chunk(
        self,
        upload_url: str,
        chunk: bytes,
        start_byte: int,
        end_byte: int,
        total_size: int,
    ) -> dict:
        """Upload a chunk to an upload session.

        Parameters
        ----------
        upload_url : str
            Upload URL from the session.
        chunk : bytes
            Chunk data.
        start_byte : int
            Start byte position.
        end_byte : int
            End byte position (inclusive).
        total_size : int
            Total file size.

        Returns
        -------
        dict
            Upload progress or completed item.
        """
        async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT) as client:
            response = await client.put(
                upload_url,
                content=chunk,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{total_size}",
                },
            )

        if response.status_code >= 400:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("error", {}).get("message", response.text)
            raise GraphAPIError(error_msg, status_code=response.status_code)

        return response.json()



    async def create_folder(
        self,
        account: LinkedAccount,
        name: str,
        parent_id: str = "root",
        conflict_behavior: str = "rename",
    ) -> DriveItem:
        """Create a new folder.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        name : str
            Folder name.
        parent_id : str
            Parent folder ID. Defaults to "root".
        conflict_behavior : str
            Conflict behavior: 'rename', 'replace', 'fail'.

        Returns
        -------
        DriveItem
            The created folder.
        """
        if parent_id == "root":
            endpoint = "/me/drive/root/children"
        else:
            endpoint = f"/me/drive/items/{parent_id}/children"

        body = {
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": conflict_behavior,
        }

        data = await self._request("POST", endpoint, account, json=body)
        return self._parse_single_item(data)

    async def update_item(
        self,
        account: LinkedAccount,
        item_id: str,
        name: str | None = None,
        parent_id: str | None = None,
    ) -> DriveItem:
        """Update an item (rename or move).

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            Item ID to update.
        name : str, optional
            New name for the item.
        parent_id : str, optional
            New parent folder ID (to move the item).

        Returns
        -------
        DriveItem
            The updated item.
        """
        body: dict[str, Any] = {}

        if name:
            body["name"] = name

        if parent_id:
            # If moving to root, use 'root' alias requires checking if it's ID or alias
            # Graph API expects ID in parentReference. If 'root' is passed, we might need
            # to resolve it or just pass it if API supports (API supports id 'root').
            body["parentReference"] = {"id": parent_id}

        if not body:
            # Nothing to update
            return await self.get_item_metadata(account, item_id)

        data = await self._request("PATCH", f"/me/drive/items/{item_id}", account, json=body)
        return self._parse_single_item(data)

    async def delete_item(
        self,
        account: LinkedAccount,
        item_id: str,
    ) -> None:
        """Delete an item (move to recycle bin).

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            Item ID to delete.
        """
        await self._request("DELETE", f"/me/drive/items/{item_id}", account)

    async def batch_delete_items(
        self,
        account: LinkedAccount,
        item_ids: list[str],
    ) -> None:
        """Delete multiple items.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_ids : list[str]
            List of item IDs to delete.
        """
        import asyncio
        
        # Limit concurrency to avoid hitting rate limits too hard
        # chunks of 5?
        semaphore = asyncio.Semaphore(5)

        async def _delete_safe(iid: str):
            async with semaphore:
                try:
                    await self.delete_item(account, iid)
                except Exception as e:
                    logger.error("Failed to delete item %s: %s", iid, e)
                    # We continue even if one fails
        
        tasks = [_delete_safe(iid) for iid in item_ids]
        await asyncio.gather(*tasks)

    async def copy_item(
        self,
        account: LinkedAccount,
        item_id: str,
        name: str | None = None,
        parent_id: str = "root",
    ) -> str:
        """Copy an item.

        Parameters
        ----------
        account : LinkedAccount
            The linked account.
        item_id : str
            Item ID to copy.
        name : str, optional
            New name for the copy.
        parent_id : str
            Target parent folder ID.

        Returns
        -------
        str
            Monitor URL for the copy operation (async).
        """
        body: dict[str, Any] = {"parentReference": {"id": parent_id}}

        if name:
            body["name"] = name

        # Copy returns 202 Accepted with Location header
        # We need to access the response headers, so we handle this manually
        # instead of using self._request which returns JSON body.
        access_token = await self._token_manager.get_valid_access_token(account)
        url = f"{GRAPH_BASE_URL}/me/drive/items/{item_id}/copy"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code != 202:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("error", {}).get("message", response.text)
            raise GraphAPIError(f"Copy failed: {error_msg}", status_code=response.status_code)

        location = response.headers.get("Location")
        if not location:
            raise GraphAPIError("Copy accepted but no monitor URL returned")

        return location
