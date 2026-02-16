"""Job management routes.

This module provides endpoints for creating and managing background jobs.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form

from backend.api.dependencies import JobServiceDep
from backend.schemas.jobs import (
    Job, JobCreate, JobMoveRequest, JobMetadataUpdateRequest,
    JobSyncRequest, JobApplyMetadataRecursiveRequest,
    JobRemoveMetadataRecursiveRequest,
    JobUndoMetadataBatchRequest,
    JobApplyRuleRequest,
)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


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
    job_service: JobServiceDep,
    limit: int = 50,
    offset: int = 0,
) -> list[Job]:
    """List recent jobs.
    
    Returns a list of jobs ordered by creation date (newest first).
    """
    return await job_service.get_jobs(limit, offset)


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
