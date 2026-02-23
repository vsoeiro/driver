"""Upload file job handler."""

import logging
import os
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.drive.transfer_service import DriveTransferService
from backend.common.upload_policy import is_large_upload
from backend.core.exceptions import DriveOrganizerError
from backend.db.models import Job, LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.item_index import (
    parent_id_from_breadcrumb,
    path_from_breadcrumb,
    upsert_item_record,
)
from backend.services.providers.factory import build_drive_client
from backend.workers.dispatcher import register_handler
from backend.workers.job_progress import JobProgressReporter

logger = logging.getLogger(__name__)


async def _job_will_retry(session: AsyncSession, raw_job_id: str | None) -> bool:
    """Return True when the next failure for this job will schedule a retry."""
    if not raw_job_id:
        return False
    try:
        job_id = UUID(str(raw_job_id))
    except (ValueError, TypeError):
        return False

    job = await session.get(Job, job_id)
    if not job:
        return False

    next_retry_count = (job.retry_count or 0) + 1
    return next_retry_count <= (job.max_retries or 0)


@register_handler("upload_file")
async def upload_file_handler(payload: dict, session: AsyncSession) -> dict:
    """Handle upload file job.

    Payload structure:
    {
        "account_id": "uuid",
        "folder_id": "str",
        "filename": "str",
        "temp_path": "str"
    }
    """
    account_id = UUID(payload["account_id"])
    folder_id = payload.get("folder_id", "root")
    filename = payload["filename"]
    temp_path = payload["temp_path"]
    progress = JobProgressReporter.from_payload(session, payload)
    await progress.set_total(1)
    await progress.update_metrics(
        total=1,
        success=0,
        failed=0,
        skipped=0,
        error_items=[],
        error_items_truncated=0,
    )

    # Ensure temp file exists
    if not os.path.exists(temp_path):
        raise DriveOrganizerError(
            f"Temporary file not found: {temp_path}", status_code=404
        )

    remove_temp_file = True

    try:
        # 1. Fetch account
        account = await session.get(LinkedAccount, account_id)
        if not account:
            raise DriveOrganizerError("Account not found", status_code=404)

        token_manager = TokenManager(session)
        client = build_drive_client(account, token_manager)
        transfer_service = DriveTransferService()

        # 2. Upload Logic
        file_size = os.path.getsize(temp_path)
        upload_kind = "large" if is_large_upload(file_size) else "small"
        logger.info(
            "Starting %s file upload for %s (%s bytes)",
            upload_kind,
            filename,
            file_size,
        )
        uploaded_item_id = await transfer_service.upload_local_file(
            client=client,
            account=account,
            local_path=temp_path,
            filename=filename,
            folder_id=folder_id,
        )
        msg = f"{upload_kind.capitalize()} file upload completed"

        if uploaded_item_id:
            uploaded_item = await client.get_item_metadata(account, uploaded_item_id)
            breadcrumb = await client.get_item_path(account, uploaded_item_id)
            await upsert_item_record(
                session,
                account_id=account.id,
                item_data=uploaded_item,
                parent_id=parent_id_from_breadcrumb(breadcrumb),
                path=path_from_breadcrumb(breadcrumb),
            )
            await session.commit()

        progress.current = 1
        await progress.update_metrics(
            total=1,
            success=1,
            failed=0,
            skipped=0,
            error_items=[],
            error_items_truncated=0,
        )
        await progress.flush(force=True)
        return {
            "filename": filename,
            "size": file_size,
            "message": msg,
            "total": 1,
            "success": 1,
            "failed": 0,
            "skipped": 0,
            "error_items": [],
            "error_items_truncated": 0,
            "metrics": {
                "total": 1,
                "success": 1,
                "failed": 0,
                "skipped": 0,
                "error_items": [],
                "error_items_truncated": 0,
            },
        }

    except Exception as e:
        try:
            if await _job_will_retry(session, payload.get("_job_id")):
                # Keep temp file for the next retry attempt.
                remove_temp_file = False
                logger.info("Preserving temp file for retry: %s", temp_path)
        except Exception:
            logger.exception(
                "Failed to evaluate retry state for upload job temp file cleanup"
            )

        progress.current = 1
        reason_text = str(e).strip() or e.__class__.__name__
        error_entry = {
            "item_name": filename,
            "reason": reason_text[:2000],
            "stage": "upload_file",
        }
        try:
            await progress.update_metrics(
                total=1,
                success=0,
                failed=1,
                skipped=0,
                error_items=[error_entry],
                error_items_truncated=0,
            )
            await progress.flush(force=True)
        except Exception:
            logger.exception(
                "Failed to persist upload progress metrics for %s", filename
            )
        logger.error(f"Upload job failed for {filename}: {e}")
        raise
    finally:
        # Cleanup temp file on success and on terminal failures.
        if remove_temp_file:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    logger.info(f"Cleaned up temp file {temp_path}")
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup temp file {temp_path}: {cleanup_error}"
                )
