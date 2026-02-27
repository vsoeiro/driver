"""AI-related background job handlers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import DriveOrganizerError
from backend.services.ai.chat_service import AIChatService
from backend.workers.dispatcher import register_handler


@register_handler("ai_generate_chat_title")
async def ai_generate_chat_title_handler(payload: dict, session: AsyncSession) -> dict:
    raw_session_id = payload.get("session_id")
    if not raw_session_id:
        raise ValueError("session_id is required")

    try:
        session_id = UUID(str(raw_session_id))
    except ValueError as exc:
        raise ValueError("Invalid session_id for ai_generate_chat_title") from exc

    service = AIChatService(session)
    try:
        updated = await service.generate_session_title_now(session_id)
    except DriveOrganizerError as exc:
        if exc.status_code == 404:
            return {
                "status": "skipped",
                "reason": "session_not_found",
                "session_id": str(session_id),
            }
        raise

    return {
        "status": "completed",
        "session_id": str(updated.id),
        "title": updated.title,
        "title_pending": updated.title_pending,
    }
