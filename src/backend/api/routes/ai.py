from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from backend.api.dependencies import DBSession
from backend.schemas.ai import (
    AIChatMessageCreateRequest,
    AIChatMessagePostResponse,
    AIChatMessageResponse,
    AIChatSessionCreateRequest,
    AIChatSessionResponse,
    AIConfirmationRequest,
    AIConfirmationResponse,
    AIToolCatalogResponse,
)
from backend.services.ai.chat_service import AIChatService

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/chat/sessions", response_model=AIChatSessionResponse)
async def create_chat_session(
    request: AIChatSessionCreateRequest,
    db: DBSession,
) -> AIChatSessionResponse:
    service = AIChatService(db)
    return await service.create_session(title=request.title)


@router.get("/chat/sessions", response_model=list[AIChatSessionResponse])
async def list_chat_sessions(
    db: DBSession,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AIChatSessionResponse]:
    service = AIChatService(db)
    return await service.list_sessions(limit=limit, offset=offset)


@router.delete("/chat/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    session_id: UUID,
    db: DBSession,
) -> None:
    service = AIChatService(db)
    await service.delete_session(session_id)


@router.post("/chat/sessions/{session_id}/title", response_model=AIChatSessionResponse)
async def generate_chat_session_title(
    session_id: UUID,
    db: DBSession,
) -> AIChatSessionResponse:
    service = AIChatService(db)
    return await service.generate_session_title(session_id)


@router.get("/chat/sessions/{session_id}/messages", response_model=list[AIChatMessageResponse])
async def get_chat_messages(
    session_id: UUID,
    db: DBSession,
    limit: int = Query(200, ge=1, le=1000),
) -> list[AIChatMessageResponse]:
    service = AIChatService(db)
    return await service.get_messages(session_id, limit=limit)


@router.post("/chat/sessions/{session_id}/messages", response_model=AIChatMessagePostResponse)
async def post_chat_message(
    session_id: UUID,
    request: AIChatMessageCreateRequest,
    db: DBSession,
) -> AIChatMessagePostResponse:
    service = AIChatService(db)
    return await service.post_message(session_id, message=request.message)


@router.post(
    "/chat/sessions/{session_id}/confirmations/{confirmation_id}",
    response_model=AIConfirmationResponse,
)
async def resolve_chat_confirmation(
    session_id: UUID,
    confirmation_id: UUID,
    request: AIConfirmationRequest,
    db: DBSession,
) -> AIConfirmationResponse:
    service = AIChatService(db)
    return await service.resolve_confirmation(
        session_id=session_id,
        confirmation_id=confirmation_id,
        approve=request.approve,
    )


@router.get("/tools/catalog", response_model=AIToolCatalogResponse)
async def get_tools_catalog(db: DBSession) -> AIToolCatalogResponse:
    service = AIChatService(db)
    return await service.tools_catalog()
