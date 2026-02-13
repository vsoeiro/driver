"""Metadata API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.dependencies import get_session
from backend.db.models import ItemMetadata, MetadataAttribute, MetadataCategory, LinkedAccount
from backend.schemas.metadata import (
    ItemMetadataCreate,
    MetadataAttributeCreate,
    MetadataCategoryCreate,
    MetadataCategory as MetadataCategorySchema,
    ItemMetadata as ItemMetadataSchema,
    MetadataAttribute as MetadataAttributeSchema,
)

router = APIRouter(prefix="/metadata", tags=["Metadata"])


# --- Categories ---
@router.get("/categories", response_model=list[MetadataCategorySchema])
async def list_categories(session: AsyncSession = Depends(get_session)):
    """List all metadata categories with their attributes."""
    query = select(MetadataCategory).options(selectinload(MetadataCategory.attributes))
    result = await session.execute(query)
    # Unique is needed when joining/loading collections to avoid duplicates in result rows if join happened
    return result.scalars().all()


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
    # Eager load attributes (will be empty)
    return db_category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: UUID, session: AsyncSession = Depends(get_session)):
    """Delete a metadata category."""
    category = await session.get(MetadataCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

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

    if existing_metadata:
        # Update existing
        existing_metadata.category_id = metadata.category_id
        existing_metadata.values = metadata.values
        # account_id and item_id should match, but we can update them i guess? No, they are keys.
        
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
