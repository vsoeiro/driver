"""OneDrive file navigation routes.

This module provides endpoints for navigating and accessing OneDrive files.
"""

import logging
import zipfile
from datetime import UTC, datetime
from fastapi import APIRouter, Query, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from starlette.background import BackgroundTask

from backend.api.dependencies import (
    LinkedAccountDep,
    GraphClientDep,
)
from backend.schemas.drive import (
    BreadcrumbItem,
    BulkDownloadRequest,
    CopyItemRequest,
    CreateFolderRequest,
    DriveItem,
    DriveListResponse,
    DriveQuota,
    PathResponse,
    UpdateItemRequest,
    UploadSession,
    UploadSessionRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/drive")

MAX_SIMPLE_UPLOAD_SIZE = 4 * 1024 * 1024  # 4MB


def _sanitize_zip_name(name: str) -> str:
    """Sanitize a filename for safe use inside ZIP archives."""
    sanitized = name.replace("\\", "_").replace("/", "_").strip().strip(".")
    return sanitized or "file"


def _ensure_unique_name(name: str, used_names: set[str]) -> str:
    """Generate a unique filename if a duplicate already exists."""
    candidate = name
    counter = 1
    while candidate.lower() in used_names:
        if "." in name:
            base, ext = name.rsplit(".", 1)
            candidate = f"{base} ({counter}).{ext}"
        else:
            candidate = f"{name} ({counter})"
        counter += 1
    used_names.add(candidate.lower())
    return candidate


@router.get("/{account_id}/files", response_model=DriveListResponse, tags=["Files"])
async def list_root_files(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
) -> DriveListResponse:
    """List files in the root of OneDrive."""
    return await graph_client.list_root_items(account)


@router.get("/{account_id}/files/{item_id}", response_model=DriveListResponse, tags=["Files"])
async def list_folder_files(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    item_id: str,
) -> DriveListResponse:
    """List files in a specific folder."""
    return await graph_client.list_folder_items(account, item_id)


@router.get("/{account_id}/file/{item_id}", response_model=DriveItem, tags=["Files"])
async def get_file_metadata(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    item_id: str,
) -> DriveItem:
    """Get metadata for a specific file or folder."""
    return await graph_client.get_item_metadata(account, item_id)


@router.get("/{account_id}/download/{item_id}", tags=["Downloads"])
async def get_download_url(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    item_id: str,
) -> dict:
    """Get a temporary download URL for a file."""
    download_url = await graph_client.get_download_url(account, item_id)
    return {"download_url": download_url}


@router.get("/{account_id}/download/{item_id}/redirect", tags=["Downloads"])
async def download_redirect(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    item_id: str,
) -> RedirectResponse:
    """Redirect to the file download URL."""
    download_url = await graph_client.get_download_url(account, item_id)
    return RedirectResponse(url=download_url)


@router.post("/{account_id}/download/zip", tags=["Downloads"])
async def download_zip(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    request: BulkDownloadRequest,
) -> FileResponse:
    """Download multiple selected files as a ZIP archive.
    
    Files are downloaded to a temporary directory on the server before being zipped
    and streamed to the client, preventing memory exhaustion.
    """
    import tempfile
    import os
    import shutil

    if not request.item_ids:
        raise HTTPException(status_code=400, detail="No files selected for ZIP download")

    # Create a temporary directory to store files
    temp_dir = tempfile.mkdtemp()
    
    try:
        files_to_zip = []
        used_names: set[str] = set()

        # Download all files to temp dir
        for item_id in request.item_ids:
            try:
                # We need a unique placeholder name for the download first
                # The actual filename will be returned by download_file_to_path
                temp_file_path = os.path.join(temp_dir, f"temp_{item_id}")
                filename = await graph_client.download_file_to_path(account, item_id, temp_file_path)
                
                safe_name = _sanitize_zip_name(filename)
                unique_name = _ensure_unique_name(safe_name, used_names)
                
                files_to_zip.append((temp_file_path, unique_name))
            except Exception as e:
                logger.error("Failed to download item %s for ZIP: %s", item_id, e)
                # Continue with other files or fail? Partial success is usually better for bulk ops
                continue

        if not files_to_zip:
             shutil.rmtree(temp_dir)
             raise HTTPException(status_code=400, detail="Failed to download any of the selected files")

        # Create ZIP file in a separate thread to avoid blocking the event loop
        def create_zip_sync(path: str, files: list[tuple[str, str]]):
            with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
                for f_path, arcname in files:
                    zip_file.write(f_path, arcname=arcname)

        zip_path = os.path.join(temp_dir, "archive.zip")
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(create_zip_sync, zip_path, files_to_zip)

        if request.archive_name:
            archive_name = _sanitize_zip_name(request.archive_name)
            if not archive_name.lower().endswith(".zip"):
                archive_name = f"{archive_name}.zip"
        else:
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            archive_name = f"drive-download-{timestamp}.zip"

        # Cleanup task
        def cleanup():
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error("Failed to clean up temp dir %s: %s", temp_dir, e)

        return FileResponse(
            path=zip_path,
            filename=archive_name,
            media_type="application/zip",
            background=BackgroundTask(cleanup)
        )
        
    except Exception:
        # If something crashes before we return the response, clean up
        shutil.rmtree(temp_dir)
        raise


@router.get("/{account_id}/search", response_model=DriveListResponse, tags=["Search & Organize"])
async def search_files(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    q: str = Query(..., min_length=1, description="Search query"),
) -> DriveListResponse:
    """Search for files and folders in OneDrive."""
    return await graph_client.search_items(account, q)


@router.get("/{account_id}/quota", response_model=DriveQuota, tags=["Usage"])
async def get_quota(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
) -> DriveQuota:
    """Get storage quota information for the OneDrive."""
    quota_data = await graph_client.get_quota(account)
    return DriveQuota(**quota_data)


@router.get("/{account_id}/recent", response_model=DriveListResponse, tags=["Search & Organize"])
async def get_recent_files(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
) -> DriveListResponse:
    """Get recently accessed files."""
    return await graph_client.get_recent_items(account)


@router.get("/{account_id}/shared", response_model=DriveListResponse, tags=["Search & Organize"])
async def get_shared_files(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
) -> DriveListResponse:
    """Get files shared with the current user."""
    return await graph_client.get_shared_with_me(account)


@router.get("/{account_id}/path/{item_id}", response_model=PathResponse, tags=["Files"])
async def get_item_path(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    item_id: str,
) -> PathResponse:
    """Get the full breadcrumb path for an item."""
    path_data = await graph_client.get_item_path(account, item_id)
    breadcrumb = [BreadcrumbItem(**item) for item in path_data]
    return PathResponse(breadcrumb=breadcrumb)


@router.post("/{account_id}/upload", response_model=DriveItem, tags=["Uploads"])
async def upload_file(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    file: UploadFile = File(...),
    folder_id: str = Query("root", description="Target folder ID"),
) -> DriveItem:
    """Upload a file (up to 4MB). For larger files, use the upload session endpoint."""
    
    try:
        # Check file size without reading entire content into memory
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        
        logger.info("Uploading file %s, size: %s bytes", file.filename, size)

        if size > MAX_SIMPLE_UPLOAD_SIZE:
             raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size is {MAX_SIMPLE_UPLOAD_SIZE // (1024*1024)}MB. Use /upload/session for larger files.",
            )

        return await graph_client.upload_small_file(
            account,
            file.filename or "unnamed_file",
            file.file, # Pass file-like object directly
            folder_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{account_id}/upload/session", response_model=UploadSession, tags=["Uploads"])
async def create_upload_session(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    request: UploadSessionRequest,
) -> UploadSession:
    """Create an upload session for large files (> 4MB)."""
    session_data = await graph_client.create_upload_session(
        account,
        request.filename,
        request.folder_id,
        request.conflict_behavior,
    )
    return UploadSession(
        upload_url=session_data["upload_url"],
        expiration=session_data["expiration"],
    )


@router.put("/{account_id}/upload/chunk", tags=["Uploads"])
async def upload_chunk(
    graph_client: GraphClientDep,
    upload_url: str = Query(..., description="Upload session URL"),
    start_byte: int = Query(..., description="Start byte position"),
    end_byte: int = Query(..., description="End byte position"),
    total_size: int = Query(..., description="Total file size"),
    file: UploadFile = File(...),
) -> dict:
    """Upload a chunk to an existing upload session."""
    chunk = await file.read()
    result = await graph_client.upload_chunk(
        upload_url,
        chunk,
        start_byte,
        end_byte,
        total_size,
    )
    return result


@router.post("/{account_id}/folders", response_model=DriveItem, status_code=201, tags=["File Management"])
async def create_folder(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    request: CreateFolderRequest,
) -> DriveItem:
    """Create a new folder."""
    return await graph_client.create_folder(
        account,
        request.name,
        request.parent_folder_id,
        request.conflict_behavior,
    )


@router.patch("/{account_id}/items/{item_id}", response_model=DriveItem, tags=["File Management"])
async def update_item(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    item_id: str,
    request: UpdateItemRequest,
) -> DriveItem:
    """Update an item (rename or move)."""
    return await graph_client.update_item(
        account,
        item_id,
        request.name,
        request.parent_folder_id,
    )


@router.post("/{account_id}/items/{item_id}/copy", status_code=202, tags=["File Management"])
async def copy_item(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    item_id: str,
    request: CopyItemRequest,
) -> dict:
    """Copy an item. Returns the monitor URL."""
    monitor_url = await graph_client.copy_item(
        account,
        item_id,
        request.name,
        request.parent_folder_id,
    )
    return {"monitor_url": monitor_url}


@router.delete("/{account_id}/items/{item_id}", status_code=204, tags=["File Management"])
async def delete_item(
    account: LinkedAccountDep,
    graph_client: GraphClientDep,
    item_id: str,
) -> None:
    """Delete an item (move to recycle bin)."""
    await graph_client.delete_item(account, item_id)

