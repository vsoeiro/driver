"""Item API routes."""

import uuid
from uuid import UUID
from typing import Optional
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, cast, Float, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.db.models import Item, ItemMetadata, LinkedAccount, MetadataCategory
from backend.schemas.items import ItemListResponse, BatchMetadataUpdate
from backend.services.metadata_versioning import apply_metadata_change

router = APIRouter(prefix="/items", tags=["Items"])


def _build_metadata_filter_conditions(filters: dict) -> list:
    conditions = []
    for attr_id, raw_filter in (filters or {}).items():
        if not attr_id:
            continue

        field_text = ItemMetadata.values[attr_id].as_string()
        field_number = cast(field_text, Float)

        if isinstance(raw_filter, dict):
            op = str(raw_filter.get("op", "eq")).lower()

            min_value = raw_filter.get("min")
            max_value = raw_filter.get("max")
            if min_value not in (None, ""):
                try:
                    conditions.append(field_number >= float(min_value))
                except (TypeError, ValueError):
                    pass
            if max_value not in (None, ""):
                try:
                    conditions.append(field_number <= float(max_value))
                except (TypeError, ValueError):
                    pass
            if min_value not in (None, "") or max_value not in (None, ""):
                continue

            value = raw_filter.get("value")
        else:
            op = "eq"
            value = raw_filter

        if value in (None, ""):
            continue

        value_str = str(value)

        if op == "eq":
            conditions.append(field_text == value_str)
        elif op == "ne":
            conditions.append(field_text != value_str)
        elif op == "contains":
            conditions.append(field_text.ilike(f"%{value_str}%"))
        elif op == "not_contains":
            conditions.append(~field_text.ilike(f"%{value_str}%"))
        elif op == "starts_with":
            conditions.append(field_text.ilike(f"{value_str}%"))
        elif op == "ends_with":
            conditions.append(field_text.ilike(f"%{value_str}"))
        elif op == "gt":
            try:
                conditions.append(field_number > float(value))
            except (TypeError, ValueError):
                pass
        elif op == "gte":
            try:
                conditions.append(field_number >= float(value))
            except (TypeError, ValueError):
                pass
        elif op == "lt":
            try:
                conditions.append(field_number < float(value))
            except (TypeError, ValueError):
                pass
        elif op == "lte":
            try:
                conditions.append(field_number <= float(value))
            except (TypeError, ValueError):
                pass

    return conditions


@router.get("", response_model=ItemListResponse)
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    sort_by: str = Query("modified_at", pattern="^(name|size|modified_at|created_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    metadata_sort_attribute_id: Optional[str] = None,
    metadata_sort_data_type: Optional[str] = Query(None, pattern="^(text|number|date|boolean|select)$"),
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
    session: AsyncSession = Depends(get_session),
):
    """List all items with pagination and filtering."""
    
    # Base query
    # Join Item with ItemMetadata
    # We use outerjoin because not all items have metadata
    query = select(Item, ItemMetadata, MetadataCategory.name.label("category_name")).outerjoin(
        ItemMetadata,
        (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id)
    ).outerjoin(
        MetadataCategory,
        ItemMetadata.category_id == MetadataCategory.id
    )

    # Filters
    if account_id:
        query = query.where(Item.account_id == account_id)
    
    if q:
        search_pattern = f"%{q}%"
        if search_fields == "name":
            query = query.where(Item.name.ilike(search_pattern))
        elif search_fields == "path":
            query = query.where(Item.path.ilike(search_pattern))
        else:
            query = query.where(
                Item.name.ilike(search_pattern) | Item.path.ilike(search_pattern)
            )

    if path_prefix:
        clean_prefix = path_prefix.rstrip("/")
        if direct_children_only:
            child_pattern = clean_prefix + "/%"
            grandchild_pattern = clean_prefix + "/%/%"
            query = query.where(
                Item.path.ilike(child_pattern),
                ~Item.path.ilike(grandchild_pattern),
            )
        else:
            child_pattern = clean_prefix + "/%"
            query = query.where(Item.path.ilike(child_pattern))
        
    if extensions:
        # Clean extensions (remove dots)
        clean_exts = [e.lstrip(".").lower() for e in extensions]
        query = query.where(Item.extension.in_(clean_exts))
        
    if item_type:
        query = query.where(Item.item_type == item_type)
        
    if size_min is not None:
        query = query.where(Item.size >= size_min)
        
    if size_max is not None:
        query = query.where(Item.size <= size_max)

    if category_id:
        query = query.where(ItemMetadata.category_id == category_id)

    if has_metadata is True:
        query = query.where(ItemMetadata.id.isnot(None))
    elif has_metadata is False:
        query = query.where(ItemMetadata.id.is_(None))

    metadata_conditions = []
    if metadata_filters:
        try:
            parsed_filters = json.loads(metadata_filters)
            metadata_conditions = _build_metadata_filter_conditions(parsed_filters)
        except Exception:
            metadata_conditions = []

    for condition in metadata_conditions:
        query = query.where(condition)

    # Count total
    count_query = select(func.count(Item.id))
    
    if account_id:
        count_query = count_query.where(Item.account_id == account_id)
    if q:
        search_pattern = f"%{q}%"
        if search_fields == "name":
            count_query = count_query.where(Item.name.ilike(search_pattern))
        elif search_fields == "path":
            count_query = count_query.where(Item.path.ilike(search_pattern))
        else:
            count_query = count_query.where(
                Item.name.ilike(search_pattern) | Item.path.ilike(search_pattern)
            )
    if path_prefix:
        clean_prefix = path_prefix.rstrip("/")
        if direct_children_only:
            child_pattern = clean_prefix + "/%"
            grandchild_pattern = clean_prefix + "/%/%"
            count_query = count_query.where(
                Item.path.ilike(child_pattern),
                ~Item.path.ilike(grandchild_pattern),
            )
        else:
            child_pattern = clean_prefix + "/%"
            count_query = count_query.where(Item.path.ilike(child_pattern))
    if extensions:
        clean_exts = [e.lstrip(".").lower() for e in extensions]
        count_query = count_query.where(Item.extension.in_(clean_exts))
    if item_type:
        count_query = count_query.where(Item.item_type == item_type)
    if size_min is not None:
        count_query = count_query.where(Item.size >= size_min)
    if size_max is not None:
        count_query = count_query.where(Item.size <= size_max)
    if category_id:
        count_query = count_query.join(
            ItemMetadata,
            (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id)
        ).where(ItemMetadata.category_id == category_id)
    if has_metadata is True:
        count_query = count_query.join(
            ItemMetadata,
            (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id),
            isouter=False
        ) if not category_id else count_query
    elif has_metadata is False:
        count_query = count_query.outerjoin(
            ItemMetadata,
            (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id)
        ).where(ItemMetadata.id.is_(None)) if not category_id else count_query

    if metadata_conditions:
        if not category_id and has_metadata is None:
            # Need to join ItemMetadata if not already joined
            count_query = count_query.join(
                ItemMetadata,
                (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id)
            )
        for condition in metadata_conditions:
            count_query = count_query.where(condition)

    total = (await session.execute(count_query)).scalar_one()

    # Sort
    sort_column = getattr(Item, sort_by)
    sort_expression = sort_column
    if metadata_sort_attribute_id:
        metadata_field_text = ItemMetadata.values[metadata_sort_attribute_id].as_string()
        if metadata_sort_data_type == "number":
            # Clean values before casting so non-numeric strings don't fail.
            numeric_text = func.nullif(
                func.regexp_replace(metadata_field_text, r"[^0-9.\-]+", "", "g"),
                "",
            )
            sort_expression = cast(numeric_text, Float)
        else:
            sort_expression = metadata_field_text

    nulls_last = case((sort_expression.is_(None), 1), else_=0)
    if sort_order == "desc":
        query = query.order_by(nulls_last.asc(), sort_expression.desc(), Item.modified_at.desc())
    else:
        query = query.order_by(nulls_last.asc(), sort_expression.asc(), Item.modified_at.desc())

    # Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute
    result = await session.execute(query)
    rows = result.all()
    
    items = []
    for row in rows:
        item, metadata, category_name = row
        
        metadata_data = None
        if metadata:
            metadata_data = {
                "id": str(metadata.id),
                "account_id": metadata.account_id,
                "item_id": metadata.item_id,
                "category_id": metadata.category_id,
                "values": metadata.values,
                "ai_suggestions": metadata.ai_suggestions or {},
                "version": metadata.version,
                "updated_at": metadata.updated_at,
                "category_name": category_name,
            }
        
        item_data = {
            "id": str(item.id),
            "account_id": item.account_id,
            "item_id": item.item_id,
            "parent_id": item.parent_id,
            "name": item.name,
            "path": item.path,
            "item_type": item.item_type,
            "mime_type": item.mime_type,
            "extension": item.extension,
            "size": item.size,
            "created_at": item.created_at,
            "modified_at": item.modified_at,
            "last_synced_at": item.last_synced_at,
            "web_url": None,
            "download_url": None,
            "metadata": metadata_data
        }
        items.append(item_data)

    return ItemListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
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
