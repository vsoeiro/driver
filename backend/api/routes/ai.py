"""AI routes (local Ollama MVP)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.db.models import MetadataAttribute, MetadataCategory
from backend.schemas.ai import (
    AIComicSuggestRequest,
    AIComicSuggestResponse,
    AIExtractMetadataRequest,
    AIExtractMetadataResponse,
    AIHealthResponse,
    AISuggestCategoryRequest,
    AISuggestCategoryResponse,
)
from backend.services.ai import AIService

router = APIRouter(prefix="/ai", tags=["AI"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=AIHealthResponse)
async def ai_health(session: AsyncSession = Depends(get_session)) -> AIHealthResponse:
    service = AIService(session)
    config, available, detail = await service.health()
    return AIHealthResponse(
        enabled=config.enabled,
        provider=config.provider,
        model=config.model,
        available=available,
        detail=detail,
    )


@router.post("/suggest-category-schema", response_model=AISuggestCategoryResponse)
async def suggest_category_schema(
    payload: AISuggestCategoryRequest,
    session: AsyncSession = Depends(get_session),
) -> AISuggestCategoryResponse:
    service = AIService(session)
    try:
        suggestion = await service.suggest_category_schema(
            document_type=payload.document_type,
            sample_text=payload.sample_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    created_category_id = None
    created_attribute_ids = []
    if payload.create_in_db:
        existing = await session.scalar(
            select(MetadataCategory.id).where(MetadataCategory.name == suggestion.category_name)
        )
        if existing:
            raise HTTPException(status_code=409, detail="Category with this name already exists")

        category = MetadataCategory(
            name=suggestion.category_name,
            description=suggestion.description,
        )
        session.add(category)
        await session.flush()
        created_category_id = category.id

        for attr in suggestion.attributes:
            db_attr = MetadataAttribute(
                category_id=category.id,
                name=attr.name,
                data_type=attr.data_type,
                is_required=attr.is_required,
                options=attr.options,
            )
            session.add(db_attr)
            await session.flush()
            created_attribute_ids.append(db_attr.id)

        await session.commit()

    return AISuggestCategoryResponse(
        suggestion=suggestion,
        created_category_id=created_category_id,
        created_attribute_ids=created_attribute_ids,
    )


@router.post("/extract-metadata", response_model=AIExtractMetadataResponse)
async def extract_metadata(
    payload: AIExtractMetadataRequest,
    session: AsyncSession = Depends(get_session),
) -> AIExtractMetadataResponse:
    service = AIService(session)
    try:
        result = await service.extract_metadata_values(
            category_id=payload.category_id,
            document_text=payload.document_text,
            account_id=payload.account_id,
            item_id=payload.item_id,
            apply_to_item=payload.apply_to_item,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    if payload.apply_to_item:
        await session.commit()

    return AIExtractMetadataResponse(**result)


@router.post("/suggest-comic-metadata", response_model=AIComicSuggestResponse)
async def suggest_comic_metadata(
    payload: AIComicSuggestRequest,
    session: AsyncSession = Depends(get_session),
) -> AIComicSuggestResponse:
    service = AIService(session)
    try:
        result = await service.suggest_comic_metadata(
            category_id=payload.category_id,
            title=payload.title,
            account_id=payload.account_id,
            item_id=payload.item_id,
            cover_account_id=payload.cover_account_id,
            cover_item_id=payload.cover_item_id,
        )
    except ValueError as exc:
        logger.warning(
            "AI comic suggestion validation error account_id=%s item_id=%s model_request_failed=%s",
            payload.account_id,
            payload.item_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "AI comic suggestion provider error account_id=%s item_id=%s",
            payload.account_id,
            payload.item_id,
        )
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    return AIComicSuggestResponse(**result)
