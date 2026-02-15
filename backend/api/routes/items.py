"""Item API routes."""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.db.models import Item, ItemMetadata, LinkedAccount, MetadataCategory
from backend.schemas.items import ItemListResponse, BatchMetadataUpdate

router = APIRouter(prefix="/items", tags=["Items"])


@router.get("", response_model=ItemListResponse)
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    sort_by: str = Query("modified_at", regex="^(name|size|modified_at|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    q: Optional[str] = None,
    search_fields: str = Query("both", regex="^(name|path|both)$"),
    path_prefix: Optional[str] = None,
    direct_children_only: bool = Query(False),
    extensions: Optional[list[str]] = Query(None),
    item_type: Optional[str] = Query(None, regex="^(file|folder)$"),
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

    if metadata_filters:
        try:
            import json
            filters = json.loads(metadata_filters)
            for attr_id, value in filters.items():
                if value:
                    # Filter ItemMetadata.values JSON where key matches attr_id and value matches
                    query = query.where(ItemMetadata.values[attr_id].as_string() == str(value))
        except Exception as e:
            # Silently ignore invalid JSON filters for now or log them
            pass

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

    if metadata_filters:
        try:
            import json
            filters = json.loads(metadata_filters)
            if not category_id and not has_metadata:
                # Need to join ItemMetadata if not already joined
                count_query = count_query.join(
                    ItemMetadata,
                    (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id)
                )
            
            for attr_id, value in filters.items():
                if value:
                    count_query = count_query.where(ItemMetadata.values[attr_id].as_string() == str(value))
        except Exception:
            pass

    total = (await session.execute(count_query)).scalar_one()

    # Sort
    sort_column = getattr(Item, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

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


@router.post("/metadata/batch", status_code=204)
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
    for item_id in batch_data.item_ids:
        if item_id in existing_records:
            # Update
            record = existing_records[item_id]
            record.category_id = batch_data.category_id
            record.values = batch_data.values
        else:
            # Create
            new_record = ItemMetadata(
                account_id=batch_data.account_id,
                item_id=item_id,
                category_id=batch_data.category_id,
                values=batch_data.values
            )
            session.add(new_record)
            
    await session.commit()
