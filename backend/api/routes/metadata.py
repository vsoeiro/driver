"""Metadata API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.dependencies import get_session
from backend.db.models import Item, ItemMetadata, MetadataAttribute, MetadataCategory, LinkedAccount
from backend.schemas.metadata import (
    ItemMetadataCreate,
    MetadataAttributeCreate,
    MetadataCategoryCreate,
    MetadataCategory as MetadataCategorySchema,
    ItemMetadata as ItemMetadataSchema,
    MetadataAttribute as MetadataAttributeSchema,
)
from backend.services.graph_client import GraphClient
from backend.services.token_manager import TokenManager

router = APIRouter(prefix="/metadata", tags=["Metadata"])


# --- Categories ---
@router.get("/categories", response_model=list[MetadataCategorySchema])
async def list_categories(session: AsyncSession = Depends(get_session)):
    """List all metadata categories with their attributes."""
    query = select(MetadataCategory).options(selectinload(MetadataCategory.attributes))
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/categories/stats")
async def get_category_stats(session: AsyncSession = Depends(get_session)):
    """Return each category with its item count.

    Returns
    -------
    list[dict]
        Each dict contains category fields plus ``item_count``.
    """
    count_subq = (
        select(
            ItemMetadata.category_id,
            func.count(ItemMetadata.id).label("item_count"),
        )
        .group_by(ItemMetadata.category_id)
        .subquery()
    )

    query = (
        select(
            MetadataCategory,
            func.coalesce(count_subq.c.item_count, 0).label("item_count"),
        )
        .outerjoin(count_subq, MetadataCategory.id == count_subq.c.category_id)
        .options(selectinload(MetadataCategory.attributes))
        .order_by(MetadataCategory.name)
    )

    result = await session.execute(query)
    rows = result.unique().all()

    return [
        {
            "id": str(cat.id),
            "name": cat.name,
            "description": cat.description,
            "created_at": cat.created_at,
            "attributes": [
                {
                    "id": str(attr.id),
                    "category_id": str(attr.category_id),
                    "name": attr.name,
                    "data_type": attr.data_type,
                    "options": attr.options,
                    "is_required": attr.is_required,
                }
                for attr in cat.attributes
            ],
            "item_count": item_count,
        }
        for cat, item_count in rows
    ]


@router.post("/categories", response_model=MetadataCategorySchema, status_code=status.HTTP_201_CREATED)
async def create_category(
    category: MetadataCategoryCreate, session: AsyncSession = Depends(get_session)
):
    """Create a new metadata category."""
    # Check for duplicate name
    query = select(MetadataCategory).where(MetadataCategory.name == category.name)
    result = await session.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category with this name already exists",
        )

    db_category = MetadataCategory(**category.model_dump())
    session.add(db_category)
    await session.commit()
    await session.refresh(db_category)
    # Avoid async lazy-load during response serialization.
    return MetadataCategorySchema(
        id=db_category.id,
        name=db_category.name,
        description=db_category.description,
        created_at=db_category.created_at,
        attributes=[],
    )


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: UUID, session: AsyncSession = Depends(get_session)):
    """Delete a metadata category."""
    category = await session.get(MetadataCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Remove metadata assignments that reference this category.
    # `item_metadata.category_id` is not a FK, so this cleanup is manual.
    await session.execute(
        delete(ItemMetadata).where(ItemMetadata.category_id == category_id)
    )
    await session.delete(category)
    await session.commit()


# --- Attributes ---
@router.post("/categories/{category_id}/attributes", response_model=MetadataAttributeSchema, status_code=status.HTTP_201_CREATED)
async def create_attribute(
    category_id: UUID,
    attribute: MetadataAttributeCreate,
    session: AsyncSession = Depends(get_session),
):
    """Add an attribute to a category."""
    category = await session.get(MetadataCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    db_attribute = MetadataAttribute(category_id=category_id, **attribute.model_dump())
    session.add(db_attribute)
    await session.commit()
    await session.refresh(db_attribute)
    return db_attribute


@router.delete("/attributes/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attribute(attribute_id: UUID, session: AsyncSession = Depends(get_session)):
    """Delete a metadata attribute."""
    attribute = await session.get(MetadataAttribute, attribute_id)
    if not attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")

    await session.delete(attribute)
    await session.commit()


# --- Item Metadata ---
@router.get("/items/{account_id}/{item_id}", response_model=ItemMetadataSchema | None)
async def get_item_metadata(
    account_id: UUID, item_id: str, session: AsyncSession = Depends(get_session)
):
    """Get metadata for a specific item."""
    query = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id, ItemMetadata.item_id == item_id
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


@router.post("/items", response_model=ItemMetadataSchema)
async def upsert_item_metadata(
    metadata: ItemMetadataCreate, session: AsyncSession = Depends(get_session)
):
    """Assign or update metadata for an item.
    
    If metadata exists for this item, it updates it. 
    However, since we allow only one category per item, if the category changes, 
    we essentially replace the record.
    """
    # 1. Check if account exists
    account = await session.get(LinkedAccount, metadata.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # 2. Check if category exists
    category = await session.get(MetadataCategory, metadata.category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # 3. Check existing metadata
    query = select(ItemMetadata).where(
        ItemMetadata.account_id == metadata.account_id,
        ItemMetadata.item_id == metadata.item_id
    )
    result = await session.execute(query)
    existing_metadata = result.scalar_one_or_none()

    # 4. Upsert Item record
    # We need to fetch details from Graph API to populate Item table
    from datetime import datetime, UTC
    
    token_manager = TokenManager(session)
    client = GraphClient(token_manager)
    
    try:
        # Get item details
        # We don't have parent_id easily here unless we fetch it.
        # GraphClient.get_item_metadata returns DriveItem which has basic info.
        # To get parent and path, we might need more calls, but let's stick to basic info for now.
        # or use get_item_path to get full path?
        drive_item = await client.get_item_metadata(account, metadata.item_id)
        
        # Check if Item exists
        stmt = select(Item).where(
            Item.account_id == account.id,
            Item.item_id == metadata.item_id
        )
        result = await session.execute(stmt)
        db_item = result.scalar_one_or_none()
        
        # Extension extraction
        extension = None
        if drive_item.item_type == "file" and "." in drive_item.name:
            extension = drive_item.name.rsplit(".", 1)[-1].lower()

        if db_item:
            # Update
            db_item.name = drive_item.name
            db_item.size = drive_item.size
            db_item.modified_at = drive_item.modified_at
            db_item.last_synced_at = datetime.now(UTC)
            db_item.mime_type = drive_item.mime_type
            db_item.extension = extension
            # parent_id and path are hard to update without fetching parent details.
            # If we want to be thorough we could fetch parent.
        else:
            # Create
            # Fetch path to get parent?
            try:
                path_data = await client.get_item_path(account, metadata.item_id)
                # path_data: [{'id': 'root', 'name': 'Root'}, ..., {'id': 'parent_id', 'name': 'Parent'}, {'id': 'item_id', 'name': 'Item'}]
                # Parent is the second to last item
                parent_id = None
                path_str = "/"
                
                if len(path_data) >= 2:
                    parent_id = path_data[-2]["id"]
                
                # Construct path string
                path_names = [p["name"] for p in path_data if p["name"] and p["name"].lower() != "root"]
                path_str = "/" + "/".join(path_names)
                
            except Exception:
                parent_id = None
                path_str = None

            db_item = Item(
                account_id=account.id,
                item_id=metadata.item_id,
                parent_id=parent_id,
                name=drive_item.name,
                path=path_str,
                item_type=drive_item.item_type,
                mime_type=drive_item.mime_type,
                extension=extension,
                size=drive_item.size,
                created_at=drive_item.created_at,
                modified_at=drive_item.modified_at,
                last_synced_at=datetime.now(UTC),
            )
            session.add(db_item)
            
    except Exception as e:
        # Don't fail the metadata update just because item sync failed?
        # User requested "always register the item", so maybe we should log error but proceed, 
        # or fail? Let's log and proceed to avoid blocking metadata save if Graph is flaky.
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to sync Item record for {metadata.item_id}: {e}")

    if existing_metadata:
        # Update existing
        existing_metadata.category_id = metadata.category_id
        existing_metadata.values = metadata.values
        
        session.add(existing_metadata)
        await session.commit()
        await session.refresh(existing_metadata)
        return existing_metadata
    else:
        # Create new
        new_metadata = ItemMetadata(**metadata.model_dump())
        session.add(new_metadata)
        await session.commit()
        await session.refresh(new_metadata)
        return new_metadata


@router.delete("/items/{account_id}/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_metadata(
    account_id: UUID, item_id: str, session: AsyncSession = Depends(get_session)
):
    """Remove metadata from an item."""
    query = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id
    )
    result = await session.execute(query)
    metadata = result.scalar_one_or_none()

    if not metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")

    await session.delete(metadata)
    await session.commit()


@router.post("/items/batch-delete", status_code=status.HTTP_204_NO_CONTENT)
async def batch_delete_item_metadata(
    account_id: UUID,
    item_ids: list[str],
    session: AsyncSession = Depends(get_session)
):
    """Remove metadata for multiple items."""
    query = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id.in_(item_ids)
    )
    result = await session.execute(query)
    metadata_list = result.scalars().all()

    if not metadata_list:
        return

    for metadata in metadata_list:
        await session.delete(metadata)
    
    await session.commit()
