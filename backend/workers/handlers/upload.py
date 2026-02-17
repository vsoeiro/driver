"""Upload file job handler."""

import logging
import os
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import DriveOrganizerError
from backend.db.models import LinkedAccount
from backend.services.item_index import parent_id_from_breadcrumb, path_from_breadcrumb, upsert_item_record
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager
from backend.workers.dispatcher import register_handler

logger = logging.getLogger(__name__)


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

    # Ensure temp file exists
    if not os.path.exists(temp_path):
        raise DriveOrganizerError(f"Temporary file not found: {temp_path}", status_code=404)

    try:
        # 1. Fetch account
        account = await session.get(LinkedAccount, account_id)
        if not account:
            raise DriveOrganizerError("Account not found", status_code=404)

        token_manager = TokenManager(session)
        client = build_drive_client(account, token_manager)

        # 2. Upload Logic
        file_size = os.path.getsize(temp_path)
        
        # Open file in binary mode
        with open(temp_path, "rb") as f:
            uploaded_item_id: str | None = None
            if file_size > 4 * 1024 * 1024:
                # Large file (> 4MB) -> Upload Session
                logger.info(f"Starting large file upload for {filename} ({file_size} bytes)")
                
                # Create session
                session_data = await client.create_upload_session(account, filename, folder_id)
                upload_url = session_data["upload_url"]
                
                # Chunked upload
                chunk_size = 327680 * 10  # ~3.2MB chunks
                
                # Upload chunks
                offset = 0
                while offset < file_size:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                        
                    end = min(offset + len(chunk), file_size) - 1
                    
                    upload_result = await client.upload_chunk(
                        upload_url,
                        chunk,
                        offset,
                        end,
                        file_size
                    )
                    if isinstance(upload_result, dict) and upload_result.get("id"):
                        uploaded_item_id = upload_result["id"]
                    
                    offset += len(chunk)
                
                msg = "Large file upload completed"
            else:
                # Small file (< 4MB) -> Simple Upload
                logger.info(f"Starting small file upload for {filename} ({file_size} bytes)")
                # Read content for small upload
                content = f.read()
                uploaded = await client.upload_small_file(account, filename, content, folder_id)
                uploaded_item_id = uploaded.id
                msg = "Small file upload completed"

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

        return {"filename": filename, "size": file_size, "message": msg}

    except Exception as e:
        logger.error(f"Upload job failed for {filename}: {e}")
        raise
    finally:
        # Cleanup temp file regardless of success/failure
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                logger.info(f"Cleaned up temp file {temp_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup temp file {temp_path}: {cleanup_error}")
