"""Job management routes.

This module provides endpoints for creating and managing background jobs.
"""

from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status, UploadFile, File, Form
from sqlalchemy import func, select

from backend.api.dependencies import DBSession, JobServiceDep
from backend.db.models import Item, ItemMetadata
from backend.schemas.jobs import (
    Job, JobAttempt, JobCreate, JobMoveRequest, JobMetadataUpdateRequest,
    JobSyncRequest, JobApplyMetadataRecursiveRequest,
    JobRemoveMetadataRecursiveRequest,
    JobUndoMetadataBatchRequest,
    JobApplyRuleRequest,
    JobExtractComicAssetsRequest,
    JobExtractLibraryComicAssetsResponse,
    JobExtractLibraryComicAssetsRequest,
    JobReindexComicCoversRequest,
)
from backend.services.jobs import JobService
from backend.services.metadata_plugins import COMICS_LIBRARY_KEY, MetadataPluginService

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _is_comic_item_already_mapped(values: dict | None, attr_ids: dict[str, str]) -> bool:
    values = values or {}
    check_fields = ("cover_item_id", "cover_account_id", "page_count", "file_format")
    for field_key in check_fields:
        attr_id = attr_ids.get(field_key)
        if not attr_id:
            continue
        value = values.get(attr_id)
        if value is not None and value != "":
            return True
    return False


async def _filter_unmapped_comic_items(
    db: DBSession,
    by_account: dict[UUID, list[str]],
) -> dict[UUID, list[str]]:
    if not by_account:
        return by_account

    library_service = MetadataPluginService(db)
    try:
        category = await library_service.ensure_active_comic_category()
    except Exception:
        # If metadata library schema is unavailable, keep current behavior (no pre-filter).
        return by_account

    attr_ids = {
        attr.plugin_field_key: str(attr.id)
        for attr in category.attributes
        if attr.plugin_field_key
    }
    if not attr_ids:
        return by_account

    filtered: dict[UUID, list[str]] = {}
    for account_id, item_ids in by_account.items():
        if not item_ids:
            continue
        stmt = select(ItemMetadata.item_id, ItemMetadata.values).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.category_id == category.id,
            ItemMetadata.item_id.in_(item_ids),
        )
        rows = (await db.execute(stmt)).all()
        already_mapped_ids = {
            str(item_id)
            for item_id, values in rows
            if _is_comic_item_already_mapped(values, attr_ids)
        }
        remaining = [item_id for item_id in item_ids if str(item_id) not in already_mapped_ids]
        if remaining:
            filtered[account_id] = remaining
    return filtered


@router.post("/move", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_move_job(
    request: JobMoveRequest,
    job_service: JobServiceDep,
) -> Job:
    """Create a new job to move items between accounts.
    
    This endpoint initiates a background job to move a file or folder from a source account
    to a destination account. The operation happens asynchronously.
    """
    payload = request.model_dump(mode='json')
    
    job_in = JobCreate(
        type="move_items",
        payload=payload,
    )
    
    return await job_service.create_job(job_in)


@router.get("/", response_model=list[Job])
async def list_jobs(
    request: Request,
    job_service: JobServiceDep,
    limit: int = 50,
    offset: int = 0,
    status_filter: list[str] | None = Query(default=None, alias="status"),
    type_filter: list[str] | None = Query(default=None, alias="type"),
    created_after: datetime | None = Query(default=None),
) -> list[Job]:
    """List recent jobs.
    
    Returns a list of jobs ordered by creation date (newest first).
    """
    raw_statuses = []
    raw_statuses.extend(status_filter or [])
    raw_statuses.extend(request.query_params.getlist("status[]"))

    statuses: list[str] = []
    for value in raw_statuses:
        if not value:
            continue
        parts = [part.strip().upper() for part in str(value).split(",")]
        statuses.extend([part for part in parts if part])

    raw_types = []
    raw_types.extend(type_filter or [])
    raw_types.extend(request.query_params.getlist("type[]"))
    types: list[str] = []
    for value in raw_types:
        if not value:
            continue
        parts = [part.strip().lower() for part in str(value).split(",")]
        types.extend([part for part in parts if part])

    return await job_service.get_jobs(
        limit=limit,
        offset=offset,
        statuses=statuses or None,
        job_types=types or None,
        created_after=created_after,
    )


@router.post("/upload", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_upload_job(
    job_service: JobServiceDep,
    file: UploadFile = File(...),
    account_id: str = Form(...),
    folder_id: str = Form("root"),
) -> Job:
    """Upload a file to be processed in the background.
    
    The file is saved to a temporary location and a job is created to upload it to OneDrive.
    """
    import shutil
    import tempfile
    import os
    from uuid import uuid4
    
    # Ensure temp directory exists
    temp_dir = os.path.join(tempfile.gettempdir(), "onedrive_uploads")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Save file to temp
    temp_filename = f"{uuid4()}_{file.filename}"
    temp_path = os.path.join(temp_dir, temp_filename)
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Create Job
    payload = {
        "account_id": account_id,
        "folder_id": folder_id,
        "filename": file.filename,
        "temp_path": temp_path,
    }
    
    
    job_in = JobCreate(
        type="upload_file",
        payload=payload,
    )
    
    return await job_service.create_job(job_in)


@router.post("/metadata-update", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_metadata_update_job(
    request: JobMetadataUpdateRequest,
    job_service: JobServiceDep,
) -> Job:
    """Create a new job to bulk update metadata."""
    
    payload = request.model_dump(mode='json')
    
    job_in = JobCreate(
        type="update_metadata",
        payload=payload,
    )
    
    return await job_service.create_job(job_in)


@router.post("/sync", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_sync_job(
    request: JobSyncRequest,
    job_service: JobServiceDep,
) -> Job:
    """Create a new job to sync items for an account."""
    
    payload = request.model_dump(mode='json')
    
    job_in = JobCreate(
        type="sync_items",
        payload=payload,
    )
    
    return await job_service.create_job(job_in)


@router.post("/apply-metadata-recursive", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_apply_metadata_recursive_job(
    request: JobApplyMetadataRecursiveRequest,
    job_service: JobServiceDep,
) -> Job:
    """Apply metadata recursively to all items under a path prefix.

    Uses the local items table — no Graph API calls needed.
    """
    payload = request.model_dump(mode='json')

    job_in = JobCreate(
        type="apply_metadata_recursive",
        payload=payload,
    )

    return await job_service.create_job(job_in)


@router.post("/remove-metadata-recursive", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_remove_metadata_recursive_job(
    request: JobRemoveMetadataRecursiveRequest,
    job_service: JobServiceDep,
) -> Job:
    """Remove metadata from all items under a path prefix."""
    payload = request.model_dump(mode='json')

    job_in = JobCreate(
        type="remove_metadata_recursive",
        payload=payload,
    )

    return await job_service.create_job(job_in)


@router.post("/metadata-undo", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_metadata_undo_job(
    request: JobUndoMetadataBatchRequest,
    job_service: JobServiceDep,
) -> Job:
    """Create a job that undoes metadata changes from a batch."""
    job_in = JobCreate(
        type="undo_metadata_batch",
        payload=request.model_dump(mode="json"),
    )
    return await job_service.create_job(job_in)


@router.post("/apply-rule", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_apply_rule_job(
    request: JobApplyRuleRequest,
    job_service: JobServiceDep,
) -> Job:
    """Create a job that applies one metadata rule."""
    job_in = JobCreate(
        type="apply_metadata_rule",
        payload=request.model_dump(mode="json"),
    )
    return await job_service.create_job(job_in)


@router.post("/comics/extract", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_extract_comic_assets_job(
    request: JobExtractComicAssetsRequest,
    job_service: JobServiceDep,
) -> Job:
    """Create a job that extracts comic cover/page metadata for selected items/folders."""
    payload = request.model_dump(mode="json")
    job_in = JobCreate(
        type="extract_comic_assets",
        payload=payload,
    )
    return await job_service.create_job(job_in)


@router.post("/comics/reindex-covers", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_reindex_comic_covers_job(
    request: JobReindexComicCoversRequest,
    job_service: JobServiceDep,
) -> Job:
    """Create a background job that re-indexes mapped comic covers using current library settings."""
    if request.library_key != COMICS_LIBRARY_KEY:
        raise HTTPException(status_code=404, detail="Unknown metadata library key for cover re-index")
    job_in = JobCreate(
        type="reindex_comic_covers",
        payload=request.model_dump(mode="json"),
    )
    return await job_service.create_job(job_in)


@router.post("/comics/extract-library", response_model=JobExtractLibraryComicAssetsResponse, status_code=status.HTTP_201_CREATED)
async def create_extract_library_comic_assets_job(
    request: JobExtractLibraryComicAssetsRequest,
    db: DBSession,
) -> JobExtractLibraryComicAssetsResponse:
    """Create chunked jobs that map all synced .cbr/.cbz files in File Library."""
    chunk_size = max(1, min(5000, int(request.chunk_size or 1000)))

    stmt = select(Item.account_id, Item.item_id).where(
        Item.item_type == "file",
        func.lower(func.coalesce(Item.extension, "")).in_(("cbr", "cbz")),
    )
    if request.account_ids:
        stmt = stmt.where(Item.account_id.in_(request.account_ids))

    rows = (await db.execute(stmt)).all()
    if not rows:
        return JobExtractLibraryComicAssetsResponse(
            total_items=0,
            total_jobs=0,
            chunk_size=chunk_size,
            job_ids=[],
        )

    by_account: dict[UUID, list[str]] = {}
    for account_id, item_id in rows:
        by_account.setdefault(account_id, []).append(item_id)

    by_account = await _filter_unmapped_comic_items(db, by_account)
    total_unmapped_items = sum(len(item_ids) for item_ids in by_account.values())
    if total_unmapped_items == 0:
        return JobExtractLibraryComicAssetsResponse(
            total_items=0,
            total_jobs=0,
            chunk_size=chunk_size,
            job_ids=[],
        )

    job_service = JobService(db)
    created_job_ids: list[UUID] = []
    for account_id, item_ids in by_account.items():
        for i in range(0, len(item_ids), chunk_size):
            chunk_ids = item_ids[i : i + chunk_size]
            job = await job_service.create_job(
                JobCreate(
                    type="extract_comic_assets",
                    payload={
                        "account_id": str(account_id),
                        "item_ids": chunk_ids,
                        "use_indexed_items": True,
                    },
                )
            )
            created_job_ids.append(job.id)

    return JobExtractLibraryComicAssetsResponse(
        total_items=total_unmapped_items,
        total_jobs=len(created_job_ids),
        chunk_size=chunk_size,
        job_ids=created_job_ids,
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    job_service: JobServiceDep,
) -> None:
    """Delete one finalized job from history."""
    try:
        await job_service.delete_job(job_id)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post("/{job_id}/cancel", response_model=Job, status_code=status.HTTP_200_OK)
async def cancel_job(
    job_id: UUID,
    job_service: JobServiceDep,
) -> Job:
    """Request cancellation for a job."""
    try:
        return await job_service.request_cancel(job_id)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post("/{job_id}/reprocess", response_model=Job, status_code=status.HTTP_201_CREATED)
async def reprocess_job(
    job_id: UUID,
    job_service: JobServiceDep,
) -> Job:
    """Clone a finalized job and queue it again."""
    try:
        return await job_service.reprocess_job(job_id)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get("/{job_id}/attempts", response_model=list[JobAttempt], status_code=status.HTTP_200_OK)
async def list_job_attempts(
    job_id: UUID,
    job_service: JobServiceDep,
    limit: int = 20,
) -> list[JobAttempt]:
    """Return execution attempt history for one job."""
    try:
        return await job_service.get_job_attempts(job_id, limit=limit)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc
