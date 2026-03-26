"""OneDrive file navigation routes.

This module provides endpoints for navigating and accessing OneDrive files.
"""

import logging
import mimetypes
import os
import tempfile
import uuid
import zipfile
import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import delete, select
from starlette.background import BackgroundTask

from backend.api.dependencies import (
    DBSession,
    DriveClientDep,
    LinkedAccountDep,
)
from backend.application.drive.download_service import DriveDownloadService
from backend.application.drive.transfer_service import DriveTransferService
from backend.common.upload_policy import MAX_RESUMABLE_UPLOAD_CHUNK_SIZE, MAX_SIMPLE_UPLOAD_SIZE
from backend.db.models import Item, ItemMetadata, LinkedAccount
from backend.schemas.drive import (
    BatchDeleteRequest,
    BreadcrumbItem,
    BulkDownloadRequest,
    ComicReaderSession,
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
from backend.services.item_index import (
    delete_item_and_descendants,
    get_item_path as get_indexed_item_path,
    parent_id_from_breadcrumb,
    path_from_breadcrumb,
    update_descendant_paths,
    upsert_item_record,
)
from backend.services.metadata_libraries.comics.reader_session_service import (
    ComicReaderSessionNotFoundError,
    ComicReaderSessionService,
    ComicReaderValidationError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/drive")
MAX_ZIP_DOWNLOAD_ITEMS = 100


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


async def _collect_local_item_ids_for_deletion(
    *,
    db: DBSession,
    account_id: uuid.UUID,
    item_id: str,
) -> list[str]:
    """Collect local indexed item ids for an item and descendants."""
    item_path = await get_indexed_item_path(db, account_id=account_id, item_id=item_id)

    if item_path:
        stmt = select(Item.item_id).where(
            Item.account_id == account_id,
            (Item.path == item_path) | (Item.path.like(f"{item_path}/%")),
        )
    else:
        stmt = select(Item.item_id).where(
            Item.account_id == account_id,
            Item.item_id == item_id,
        )

    rows = await db.execute(stmt)
    return [row[0] for row in rows.all()]


async def _refresh_index_from_provider(
    *,
    db: DBSession,
    account: LinkedAccount,
    graph_client: DriveClientDep,
    item_id: str,
) -> DriveItem:
    """Fetch current provider metadata/path and upsert into local items index."""
    item = await graph_client.get_item_metadata(account, item_id)
    breadcrumb = await graph_client.get_item_path(account, item_id)
    item_path = path_from_breadcrumb(breadcrumb)
    parent_id = parent_id_from_breadcrumb(breadcrumb)
    await upsert_item_record(
        db,
        account_id=account.id,
        item_data=item,
        parent_id=parent_id,
        path=item_path,
    )
    return item


@router.get("/{account_id}/files", response_model=DriveListResponse, tags=["Files"])
async def list_root_files(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    page_size: int = Query(50, ge=1, le=200),
    next_link: str | None = Query(
        None, description="Provider pagination cursor/next link"
    ),
) -> DriveListResponse:
    """List files in the root of OneDrive."""
    if next_link:
        return await graph_client.list_items_by_next_link(account, next_link)
    return await graph_client.list_root_items(account, page_size=page_size)


@router.get(
    "/{account_id}/files/{item_id}", response_model=DriveListResponse, tags=["Files"]
)
async def list_folder_files(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    item_id: str,
    page_size: int = Query(50, ge=1, le=200),
    next_link: str | None = Query(
        None, description="Provider pagination cursor/next link"
    ),
) -> DriveListResponse:
    """List files in a specific folder."""
    if next_link:
        return await graph_client.list_items_by_next_link(account, next_link)
    return await graph_client.list_folder_items(account, item_id, page_size=page_size)


@router.get("/{account_id}/file/{item_id}", response_model=DriveItem, tags=["Files"])
async def get_file_metadata(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    item_id: str,
) -> DriveItem:
    """Get metadata for a specific file or folder."""
    return await graph_client.get_item_metadata(account, item_id)


@router.get("/{account_id}/download/{item_id}", tags=["Downloads"])
async def get_download_url(
    account_id: str,
    db: DBSession,
    item_id: str,
    auto_resolve_account: bool = Query(
        False,
        description="If true, on 400/404 from the current account it will try other linked accounts.",
    ),
) -> dict:
    """Get a temporary download URL for a file."""
    download_url = await DriveDownloadService(db).get_download_url(
        account_id=account_id,
        item_id=item_id,
        auto_resolve_account=auto_resolve_account,
    )
    return {"download_url": download_url}


@router.get("/{account_id}/download/{item_id}/content", tags=["Downloads"])
async def download_content(
    account_id: str,
    db: DBSession,
    item_id: str,
    auto_resolve_account: bool = Query(
        False,
        description="If true, on 400/404 from the current account it will try other linked accounts.",
    ),
) -> Response:
    """Proxy file bytes through backend so browser <img> can load provider-protected files."""
    filename, content = await DriveDownloadService(db).download_file_bytes(
        account_id=account_id,
        item_id=item_id,
        auto_resolve_account=auto_resolve_account,
    )

    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post(
    "/{account_id}/reader/comics/{item_id}/sessions",
    response_model=ComicReaderSession,
    tags=["Reader"],
)
async def create_comic_reader_session(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    db: DBSession,
    item_id: str,
) -> ComicReaderSession:
    """Create or reuse a temporary comic reader session for one archive item."""
    service = ComicReaderSessionService(db)
    try:
        return await service.create_session(
            account_id=account.id,
            item_id=item_id,
            account=account,
            graph_client=graph_client,
        )
    except ComicReaderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/{account_id}/reader/comics/sessions/{session_id}/pages/{page_index}",
    tags=["Reader"],
)
async def get_comic_reader_page(
    account: LinkedAccountDep,
    db: DBSession,
    session_id: str,
    page_index: int,
) -> FileResponse:
    """Return one extracted comic page for an active reader session."""
    service = ComicReaderSessionService(db)
    try:
        payload = await service.get_page_payload(
            account_id=account.id,
            session_id=session_id,
            page_index=page_index,
        )
    except ComicReaderSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        path=payload.path,
        media_type=payload.media_type,
        headers={"Cache-Control": "private, max-age=900"},
    )


@router.get("/{account_id}/download/{item_id}/redirect", tags=["Downloads"])
async def download_redirect(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    item_id: str,
) -> RedirectResponse:
    """Redirect to the file download URL."""
    download_url = await graph_client.get_download_url(account, item_id)
    return RedirectResponse(url=download_url)


@router.post("/{account_id}/download/zip", tags=["Downloads"])
async def download_zip(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    request: BulkDownloadRequest,
) -> FileResponse:
    """Download multiple selected files as a ZIP archive.

    Files are downloaded to a temporary directory on the server before being zipped
    and streamed to the client, preventing memory exhaustion.
    """
    import shutil

    if not request.item_ids:
        raise HTTPException(
            status_code=400, detail="No files selected for ZIP download"
        )
    if len(request.item_ids) > MAX_ZIP_DOWNLOAD_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=f"ZIP download supports at most {MAX_ZIP_DOWNLOAD_ITEMS} items per request.",
        )

    # Create a temporary directory to store files
    temp_dir = tempfile.mkdtemp()

    try:
        files_to_zip = []
        used_names: set[str] = set()

        semaphore = asyncio.Semaphore(4)
        files_lock = asyncio.Lock()

        async def _download_one(item_id: str) -> None:
            try:
                async with semaphore:
                    temp_file_path = os.path.join(
                        temp_dir, f"tmp_{uuid.uuid4().hex}_{item_id}"
                    )
                    filename = await graph_client.download_file_to_path(
                        account, item_id, temp_file_path
                    )
                    safe_name = _sanitize_zip_name(filename)
                    async with files_lock:
                        unique_name = _ensure_unique_name(safe_name, used_names)
                        files_to_zip.append((temp_file_path, unique_name))
            except Exception as e:
                logger.error("Failed to download item %s for ZIP: %s", item_id, e)

        await asyncio.gather(*[_download_one(item_id) for item_id in request.item_ids])

        if not files_to_zip:
            shutil.rmtree(temp_dir)
            raise HTTPException(
                status_code=400, detail="Failed to download any of the selected files"
            )

        # Create ZIP file in a separate thread to avoid blocking the event loop
        def create_zip_sync(path: str, files: list[tuple[str, str]]):
            with zipfile.ZipFile(
                path, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as zip_file:
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
            background=BackgroundTask(cleanup),
        )

    except Exception:
        # If something crashes before we return the response, clean up
        shutil.rmtree(temp_dir)
        raise


@router.get(
    "/{account_id}/search", response_model=DriveListResponse, tags=["Search & Organize"]
)
async def search_files(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    q: str = Query(..., min_length=1, description="Search query"),
) -> DriveListResponse:
    """Search for files and folders in OneDrive."""
    return await graph_client.search_items(account, q)


@router.get("/{account_id}/quota", response_model=DriveQuota, tags=["Usage"])
async def get_quota(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
) -> DriveQuota:
    """Get storage quota information for the OneDrive."""
    quota_data = await graph_client.get_quota(account)
    return DriveQuota(**quota_data)


@router.get(
    "/{account_id}/recent", response_model=DriveListResponse, tags=["Search & Organize"]
)
async def get_recent_files(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
) -> DriveListResponse:
    """Get recently accessed files."""
    return await graph_client.get_recent_items(account)


@router.get(
    "/{account_id}/shared", response_model=DriveListResponse, tags=["Search & Organize"]
)
async def get_shared_files(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
) -> DriveListResponse:
    """Get files shared with the current user."""
    return await graph_client.get_shared_with_me(account)


@router.get("/{account_id}/path/{item_id}", response_model=PathResponse, tags=["Files"])
async def get_item_path(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    item_id: str,
) -> PathResponse:
    """Get the full breadcrumb path for an item."""
    path_data = await graph_client.get_item_path(account, item_id)
    breadcrumb = [BreadcrumbItem(**item) for item in path_data]
    return PathResponse(breadcrumb=breadcrumb)


@router.post("/{account_id}/upload", response_model=DriveItem, tags=["Uploads"])
async def upload_file(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    db: DBSession,
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
                detail=f"File too large. Max size is {MAX_SIMPLE_UPLOAD_SIZE // (1024 * 1024)}MB. Use /upload/session for larger files.",
            )

        transfer_service = DriveTransferService()
        uploaded_item_id = await transfer_service.upload_file_object(
            client=graph_client,
            account=account,
            file_obj=file.file,
            filename=file.filename or "unnamed_file",
            folder_id=folder_id,
        )
        if not uploaded_item_id:
            raise HTTPException(
                status_code=502, detail="Upload did not return an item id"
            )
        uploaded = await graph_client.get_item_metadata(
            account,
            uploaded_item_id,
        )
        await _refresh_index_from_provider(
            db=db,
            account=account,
            graph_client=graph_client,
            item_id=uploaded.id,
        )
        await db.commit()
        return uploaded
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Upload failed. Check server logs for details.",
        )


@router.post(
    "/{account_id}/upload/session", response_model=UploadSession, tags=["Uploads"]
)
async def create_upload_session(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
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
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    db: DBSession,
    upload_url: str = Query(..., description="Upload session URL"),
    start_byte: int = Query(..., description="Start byte position"),
    end_byte: int = Query(..., description="End byte position"),
    total_size: int = Query(..., description="Total file size"),
    file: UploadFile = File(...),
) -> dict:
    """Upload a chunk to an existing upload session."""
    if start_byte < 0 or end_byte < start_byte:
        raise HTTPException(status_code=400, detail="Invalid byte range")
    if total_size <= 0:
        raise HTTPException(status_code=400, detail="Invalid total_size")
    if end_byte >= total_size:
        raise HTTPException(status_code=400, detail="end_byte must be less than total_size")

    chunk = await file.read()
    expected_chunk_size = (end_byte - start_byte) + 1
    if expected_chunk_size != len(chunk):
        raise HTTPException(status_code=400, detail="Chunk size does not match byte range")
    if len(chunk) > MAX_RESUMABLE_UPLOAD_CHUNK_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Chunk too large. Max chunk size is {MAX_RESUMABLE_UPLOAD_CHUNK_SIZE // (1024 * 1024)}MB.",
        )

    result = await graph_client.upload_chunk(
        upload_url,
        chunk,
        start_byte,
        end_byte,
        total_size,
        account=account,
    )
    item_id = result.get("id") if isinstance(result, dict) else None
    if item_id:
        await _refresh_index_from_provider(
            db=db,
            account=account,
            graph_client=graph_client,
            item_id=item_id,
        )
        await db.commit()
    return result


@router.post(
    "/{account_id}/folders",
    response_model=DriveItem,
    status_code=201,
    tags=["File Management"],
)
async def create_folder(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    db: DBSession,
    request: CreateFolderRequest,
) -> DriveItem:
    """Create a new folder."""
    created = await graph_client.create_folder(
        account,
        request.name,
        request.parent_folder_id,
        request.conflict_behavior,
    )
    await _refresh_index_from_provider(
        db=db,
        account=account,
        graph_client=graph_client,
        item_id=created.id,
    )
    await db.commit()
    return created


@router.patch(
    "/{account_id}/items/{item_id}", response_model=DriveItem, tags=["File Management"]
)
async def update_item(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    db: DBSession,
    item_id: str,
    request: UpdateItemRequest,
) -> DriveItem:
    """Update an item (rename or move)."""
    old_path = await db.scalar(
        select(Item.path).where(
            Item.account_id == account.id,
            Item.item_id == item_id,
        )
    )

    updated = await graph_client.update_item(
        account,
        item_id,
        request.name,
        request.parent_folder_id,
    )
    refreshed = await _refresh_index_from_provider(
        db=db,
        account=account,
        graph_client=graph_client,
        item_id=updated.id,
    )
    new_path = await db.scalar(
        select(Item.path).where(
            Item.account_id == account.id,
            Item.item_id == item_id,
        )
    )
    if (
        refreshed.item_type == "folder"
        and old_path
        and new_path
        and old_path != new_path
    ):
        await update_descendant_paths(
            db,
            account_id=account.id,
            old_prefix=old_path,
            new_prefix=new_path,
        )
    await db.commit()
    return updated


@router.post(
    "/{account_id}/items/{item_id}/copy", status_code=202, tags=["File Management"]
)
async def copy_item(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
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


@router.delete(
    "/{account_id}/items/{item_id}", status_code=204, tags=["File Management"]
)
async def delete_item(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    db: DBSession,
    item_id: str,
) -> None:
    """Delete an item (move to recycle bin)."""
    await graph_client.delete_item(account, item_id)
    item_ids = await _collect_local_item_ids_for_deletion(
        db=db,
        account_id=account.id,
        item_id=item_id,
    )
    if item_ids:
        await db.execute(
            delete(ItemMetadata).where(
                ItemMetadata.account_id == account.id,
                ItemMetadata.item_id.in_(item_ids),
            )
        )
    await delete_item_and_descendants(db, account_id=account.id, item_id=item_id)
    await db.commit()


@router.post(
    "/{account_id}/items/batch-delete", status_code=204, tags=["File Management"]
)
async def batch_delete_items(
    account: LinkedAccountDep,
    graph_client: DriveClientDep,
    db: DBSession,
    request: BatchDeleteRequest,
) -> None:
    """Delete multiple items (move to recycle bin)."""
    if not request.item_ids:
        return

    await graph_client.batch_delete_items(account, request.item_ids)
    item_ids_to_clear_metadata: set[str] = set()
    for item_id in request.item_ids:
        matched_ids = await _collect_local_item_ids_for_deletion(
            db=db,
            account_id=account.id,
            item_id=item_id,
        )
        item_ids_to_clear_metadata.update(matched_ids)

    if item_ids_to_clear_metadata:
        await db.execute(
            delete(ItemMetadata).where(
                ItemMetadata.account_id == account.id,
                ItemMetadata.item_id.in_(list(item_ids_to_clear_metadata)),
            )
        )

    for item_id in request.item_ids:
        await delete_item_and_descendants(db, account_id=account.id, item_id=item_id)
    await db.commit()
