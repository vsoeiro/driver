"""Item API routes."""

import uuid
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.metadata.item_query_service import ItemQueryService
from backend.api.dependencies import get_session
from backend.db.models import ItemMetadata, LinkedAccount, MetadataCategory
from backend.schemas.items import ItemListResponse, BatchMetadataUpdate, SimilarItemsReportResponse
from backend.services.metadata_versioning import apply_metadata_change

router = APIRouter(prefix="/items", tags=["Items"])


@router.get("", response_model=ItemListResponse)
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = Query("modified_at", pattern="^(name|size|modified_at|created_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    metadata_sort_attribute_id: Optional[str] = None,
    metadata_sort_data_type: Optional[str] = Query(None, pattern="^(text|number|date|boolean|select|tags)$"),
    q: Optional[str] = None,
    search_fields: str = Query("both", pattern="^(name|path|both)$"),
    path_prefix: Optional[str] = None,
    direct_children_only: bool = Query(False),
    extensions: Optional[list[str]] = Query(None),
    item_type: Optional[str] = Query(None, pattern="^(file|folder)$"),
    size_min: Optional[int] = Query(None, ge=0),
    size_max: Optional[int] = Query(None, ge=0),
    account_id: Optional[UUID] = None,
    category_id: Optional[UUID] = None,
    has_metadata: Optional[bool] = None,
    metadata_filters: Optional[str] = Query(None, alias="metadata"),  # JSON string: {"attr_id": "value"}
    include_total: bool = Query(True, description="If false, skips expensive total count query."),
    session: AsyncSession = Depends(get_session),
):
    """List all items with pagination and filtering."""
    service = ItemQueryService(session)
    return await service.list_items(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        metadata_sort_attribute_id=metadata_sort_attribute_id,
        metadata_sort_data_type=metadata_sort_data_type,
        q=q,
        search_fields=search_fields,
        path_prefix=path_prefix,
        direct_children_only=direct_children_only,
        extensions=extensions,
        item_type=item_type,
        size_min=size_min,
        size_max=size_max,
        account_id=account_id,
        category_id=category_id,
        has_metadata=has_metadata,
        metadata_filters=metadata_filters,
        include_total=include_total,
    )


@router.get("/similar-report", response_model=SimilarItemsReportResponse)
async def get_similar_items_report(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    account_id: Optional[UUID] = None,
    scope: str = Query("all", pattern="^(all|same_account|cross_account)$"),
    sort_by: str = Query("relevance", pattern="^(relevance|name|size)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    extensions: Optional[list[str]] = Query(None),
    hide_low_priority: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    """Generate a report for possible duplicate files."""
    service = ItemQueryService(session)
    return await service.get_similar_items_report(
        page=page,
        page_size=page_size,
        account_id=account_id,
        scope=scope,
        sort_by=sort_by,
        sort_order=sort_order,
        extensions=extensions,
        hide_low_priority=hide_low_priority,
    )


@router.post("/metadata/batch")
async def batch_update_metadata(
    batch_data: BatchMetadataUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Batch update metadata for multiple items."""
    
    # Verify account and category
    account = await session.get(LinkedAccount, batch_data.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
        
    category = await session.get(MetadataCategory, batch_data.category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # 1. Fetch existing metadata records
    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == batch_data.account_id,
        ItemMetadata.item_id.in_(batch_data.item_ids)
    )
    result = await session.execute(stmt)
    existing_records = {r.item_id: r for r in result.scalars().all()}

    # 2. Iterate and upsert
    batch_id = uuid.uuid4()
    updated = 0
    created = 0
    for item_id in batch_data.item_ids:
        existing = existing_records.get(item_id)
        if existing and existing.category_id == batch_data.category_id:
            merged_values = dict(existing.values or {})
            merged_values.update(batch_data.values or {})
        else:
            merged_values = dict(batch_data.values or {})
        change = await apply_metadata_change(
            session,
            account_id=batch_data.account_id,
            item_id=item_id,
            category_id=batch_data.category_id,
            values=merged_values,
            batch_id=batch_id,
        )
        if change["changed"]:
            if existing:
                updated += 1
            else:
                created += 1

    await session.commit()
    return {
        "batch_id": str(batch_id),
        "updated": updated,
        "created": created,
        "total": len(batch_data.item_ids),
    }
