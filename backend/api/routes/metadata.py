"""Metadata API routes."""

import uuid
from uuid import UUID
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.dependencies import get_session
from backend.db.models import (
    Item,
    ItemMetadata,
    ItemMetadataHistory,
    MetadataAttribute,
    MetadataCategory,
    MetadataRule,
    LinkedAccount,
)
from backend.schemas.metadata import (
    ItemMetadataCreate,
    ItemMetadataAIFieldActionRequest,
    ItemMetadataAISuggestionsUpdate,
    MetadataAttributeCreate,
    MetadataAttributeUpdate,
    MetadataCategoryCreate,
    MetadataCategory as MetadataCategorySchema,
    ItemMetadata as ItemMetadataSchema,
    ItemMetadataHistory as ItemMetadataHistorySchema,
    MetadataAttribute as MetadataAttributeSchema,
    MetadataPlugin as MetadataPluginSchema,
    MetadataRule as MetadataRuleSchema,
    MetadataRuleCreate,
    MetadataRulePreviewRequest,
    MetadataRulePreviewResponse,
    MetadataRuleUpdate,
)
from backend.services.metadata_plugins import COMIC_PLUGIN_KEY, MetadataPluginService
from backend.services.metadata_versioning import apply_metadata_change, normalize_metadata_values, undo_metadata_batch
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager

router = APIRouter(prefix="/metadata", tags=["Metadata"])


def _to_json_compatible(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_json_compatible(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_compatible(v) for v in value]
    return value


def _normalize_ai_suggestions_payload(raw: dict | None) -> dict[str, dict]:
    if not raw:
        return {}
    normalized: dict[str, dict] = {}
    for attr_id, suggestion in raw.items():
        if suggestion is None:
            continue
        if hasattr(suggestion, "model_dump"):
            suggestion = suggestion.model_dump(mode="json")
        if isinstance(suggestion, dict):
            value = _to_json_compatible(suggestion.get("value"))
            confidence = _to_json_compatible(suggestion.get("confidence"))
            source = suggestion.get("source") or "ai"
            model = _to_json_compatible(suggestion.get("model"))
            notes = _to_json_compatible(suggestion.get("notes"))
            generated_at = _to_json_compatible(suggestion.get("generated_at"))
        else:
            value = _to_json_compatible(suggestion)
            confidence = None
            source = "ai"
            model = None
            notes = None
            generated_at = None
        if generated_at is None:
            generated_at = datetime.now(UTC).isoformat()
        normalized[str(attr_id)] = {
            "value": value,
            "confidence": confidence,
            "source": source,
            "model": model,
            "notes": notes,
            "generated_at": generated_at,
        }
    return normalized


async def _validate_rule_configuration(session: AsyncSession, payload: dict) -> None:
    if payload.get("apply_rename") and not (payload.get("rename_template") or "").strip():
        raise HTTPException(status_code=400, detail="rename_template is required when apply_rename is true")

    if payload.get("apply_move"):
        destination_folder_id = (payload.get("destination_folder_id") or "").strip()
        if not destination_folder_id:
            raise HTTPException(status_code=400, detail="destination_folder_id is required when apply_move is true")

    if not payload.get("apply_metadata", True) and not payload.get("apply_rename") and not payload.get("apply_move"):
        raise HTTPException(status_code=400, detail="At least one action must be enabled")

    destination_account_id = payload.get("destination_account_id")
    if destination_account_id:
        linked = await session.get(LinkedAccount, destination_account_id)
        if not linked:
            raise HTTPException(status_code=404, detail="Destination account not found")


# --- Categories ---
@router.get("/categories", response_model=list[MetadataCategorySchema])
async def list_categories(session: AsyncSession = Depends(get_session)):
    """List all metadata categories with their attributes."""
    query = (
        select(MetadataCategory)
        .where(MetadataCategory.is_active.is_(True))
        .options(selectinload(MetadataCategory.attributes))
        .order_by(MetadataCategory.name.asc())
    )
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
        .where(MetadataCategory.is_active.is_(True))
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
            "is_active": cat.is_active,
            "managed_by_plugin": cat.managed_by_plugin,
            "plugin_key": cat.plugin_key,
            "is_locked": cat.is_locked,
            "created_at": cat.created_at,
            "attributes": [
                {
                    "id": str(attr.id),
                    "category_id": str(attr.category_id),
                    "name": attr.name,
                    "data_type": attr.data_type,
                    "options": attr.options,
                    "is_required": attr.is_required,
                    "managed_by_plugin": attr.managed_by_plugin,
                    "plugin_key": attr.plugin_key,
                    "plugin_field_key": attr.plugin_field_key,
                    "is_locked": attr.is_locked,
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
    if category.is_locked or category.managed_by_plugin:
        raise HTTPException(
            status_code=400,
            detail="Plugin-managed category cannot be deleted. Deactivate the plugin instead.",
        )

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
    if not category.is_active:
        raise HTTPException(status_code=400, detail="Cannot add attributes to an inactive category")

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
    if attribute.is_locked or attribute.managed_by_plugin:
        raise HTTPException(status_code=400, detail="Plugin-managed attribute cannot be deleted")

    await session.delete(attribute)
    await session.commit()


@router.patch("/attributes/{attribute_id}", response_model=MetadataAttributeSchema)
async def update_attribute(
    attribute_id: UUID,
    attribute: MetadataAttributeUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a metadata attribute."""
    db_attribute = await session.get(MetadataAttribute, attribute_id)
    if not db_attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")
    if db_attribute.is_locked or db_attribute.managed_by_plugin:
        raise HTTPException(status_code=400, detail="Plugin-managed attribute cannot be edited")

    updates = attribute.model_dump(exclude_unset=True)
    if "data_type" in updates and updates["data_type"] != "select":
        updates["options"] = None

    for key, value in updates.items():
        setattr(db_attribute, key, value)

    await session.commit()
    await session.refresh(db_attribute)
    return db_attribute


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
    if not category.is_active:
        raise HTTPException(status_code=400, detail="Category is inactive")

    # 3. Upsert Item record
    # We need to fetch details from Graph API to populate Item table
    from datetime import datetime, UTC
    
    token_manager = TokenManager(session)
    client = build_drive_client(account, token_manager)
    
    try:
        # Get item details
        # We don't have parent_id easily here unless we fetch it.
        # Provider client returns DriveItem with basic info.
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

    await apply_metadata_change(
        session,
        account_id=metadata.account_id,
        item_id=metadata.item_id,
        category_id=metadata.category_id,
        values=normalize_metadata_values(metadata.values),
    )
    await session.commit()

    query = select(ItemMetadata).where(
        ItemMetadata.account_id == metadata.account_id,
        ItemMetadata.item_id == metadata.item_id,
    )
    refreshed = await session.execute(query)
    current = refreshed.scalar_one_or_none()
    if not current:
        raise HTTPException(status_code=500, detail="Failed to save metadata")
    current.ai_suggestions = _normalize_ai_suggestions_payload(metadata.ai_suggestions)
    await session.commit()
    return current


@router.patch("/items/{account_id}/{item_id}/ai-suggestions", response_model=ItemMetadataSchema)
async def update_item_ai_suggestions(
    account_id: UUID,
    item_id: str,
    payload: ItemMetadataAISuggestionsUpdate,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id,
    )
    result = await session.execute(stmt)
    metadata = result.scalar_one_or_none()
    if not metadata:
        metadata = ItemMetadata(
            account_id=account_id,
            item_id=item_id,
            category_id=payload.category_id,
            values={},
            ai_suggestions={},
            version=1,
        )
        session.add(metadata)
        await session.flush()
    else:
        metadata.category_id = payload.category_id

    metadata.ai_suggestions = _normalize_ai_suggestions_payload(payload.suggestions)
    await session.commit()
    await session.refresh(metadata)
    return metadata


@router.post("/items/{account_id}/{item_id}/ai-suggestions/accept", response_model=ItemMetadataSchema)
async def accept_item_ai_suggestion(
    account_id: UUID,
    item_id: str,
    payload: ItemMetadataAIFieldActionRequest,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id,
    )
    result = await session.execute(stmt)
    metadata = result.scalar_one_or_none()
    if not metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")

    attr_id = str(payload.attribute_id)
    suggestions = metadata.ai_suggestions or {}
    selected = suggestions.get(attr_id)
    if not selected:
        raise HTTPException(status_code=404, detail="AI suggestion not found for this attribute")

    merged_values = dict(metadata.values or {})
    merged_values[attr_id] = selected.get("value")

    await apply_metadata_change(
        session,
        account_id=account_id,
        item_id=item_id,
        category_id=payload.category_id,
        values=merged_values,
    )

    refreshed_row = await session.execute(
        select(ItemMetadata).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.item_id == item_id,
        )
    )
    refreshed = refreshed_row.scalar_one_or_none()
    if refreshed is None:
        raise HTTPException(status_code=500, detail="Failed to update metadata")

    refreshed_suggestions = dict(refreshed.ai_suggestions or {})
    refreshed_suggestions.pop(attr_id, None)
    refreshed.ai_suggestions = refreshed_suggestions
    await session.commit()
    await session.refresh(refreshed)
    return refreshed


@router.post("/items/{account_id}/{item_id}/ai-suggestions/reject", response_model=ItemMetadataSchema)
async def reject_item_ai_suggestion(
    account_id: UUID,
    item_id: str,
    payload: ItemMetadataAIFieldActionRequest,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id,
    )
    result = await session.execute(stmt)
    metadata = result.scalar_one_or_none()
    if not metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")

    attr_id = str(payload.attribute_id)
    suggestions = dict(metadata.ai_suggestions or {})
    if attr_id not in suggestions:
        raise HTTPException(status_code=404, detail="AI suggestion not found for this attribute")

    suggestions.pop(attr_id, None)
    metadata.ai_suggestions = suggestions
    if payload.category_id:
        metadata.category_id = payload.category_id
    await session.commit()
    await session.refresh(metadata)
    return metadata


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

    await apply_metadata_change(
        session,
        account_id=account_id,
        item_id=item_id,
        category_id=None,
        values=None,
    )
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

    batch_id = uuid.uuid4()
    for metadata in metadata_list:
        await apply_metadata_change(
            session,
            account_id=metadata.account_id,
            item_id=metadata.item_id,
            category_id=None,
            values=None,
            batch_id=batch_id,
        )
    
    await session.commit()


@router.get(
    "/items/{account_id}/{item_id}/history",
    response_model=list[ItemMetadataHistorySchema],
)
async def get_item_metadata_history(
    account_id: UUID,
    item_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List metadata change history for one item."""
    stmt = (
        select(ItemMetadataHistory)
        .where(
            ItemMetadataHistory.account_id == account_id,
            ItemMetadataHistory.item_id == item_id,
        )
        .order_by(ItemMetadataHistory.created_at.desc())
        .limit(200)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("/batches/{batch_id}/undo")
async def undo_metadata_batch_route(
    batch_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Undo metadata changes from a batch id."""
    stats = await undo_metadata_batch(session, batch_id=batch_id)
    await session.commit()
    return {"batch_id": str(batch_id), **stats}


@router.get("/rules", response_model=list[MetadataRuleSchema])
async def list_metadata_rules(session: AsyncSession = Depends(get_session)):
    """List metadata rules by priority."""
    stmt = select(MetadataRule).order_by(MetadataRule.priority.asc(), MetadataRule.created_at.asc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("/rules", response_model=MetadataRuleSchema, status_code=status.HTTP_201_CREATED)
async def create_metadata_rule(
    rule: MetadataRuleCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a metadata rule."""
    category = await session.get(MetadataCategory, rule.target_category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    payload = rule.model_dump()
    await _validate_rule_configuration(session, payload)
    db_rule = MetadataRule(**payload)
    session.add(db_rule)
    await session.commit()
    await session.refresh(db_rule)
    return db_rule


@router.patch("/rules/{rule_id}", response_model=MetadataRuleSchema)
async def update_metadata_rule(
    rule_id: UUID,
    rule: MetadataRuleUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a metadata rule."""
    db_rule = await session.get(MetadataRule, rule_id)
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    updates = rule.model_dump(exclude_unset=True)
    if "target_category_id" in updates:
        category = await session.get(MetadataCategory, updates["target_category_id"])
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

    for key, value in updates.items():
        setattr(db_rule, key, value)

    effective_payload = {
        "apply_metadata": db_rule.apply_metadata,
        "apply_rename": db_rule.apply_rename,
        "rename_template": db_rule.rename_template,
        "apply_move": db_rule.apply_move,
        "destination_account_id": db_rule.destination_account_id,
        "destination_folder_id": db_rule.destination_folder_id,
        "destination_path_template": db_rule.destination_path_template,
    }
    effective_payload.update({k: v for k, v in updates.items() if k in effective_payload})
    await _validate_rule_configuration(session, effective_payload)

    await session.commit()
    await session.refresh(db_rule)
    return db_rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metadata_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete a metadata rule."""
    db_rule = await session.get(MetadataRule, rule_id)
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await session.delete(db_rule)
    await session.commit()


@router.post("/rules/preview", response_model=MetadataRulePreviewResponse)
async def preview_metadata_rule(
    request: MetadataRulePreviewRequest,
    session: AsyncSession = Depends(get_session),
):
    """Preview how many items would be changed by a rule."""
    await _validate_rule_configuration(session, request.model_dump())
    query = select(Item).where(Item.path.isnot(None))
    if request.account_id:
        query = query.where(Item.account_id == request.account_id)
    if request.path_prefix:
        prefix = request.path_prefix.rstrip("/")
        query = query.where(Item.path.ilike(f"{prefix}/%"))
    if request.path_contains:
        query = query.where(Item.path.ilike(f"%{request.path_contains}%"))
    if not request.include_folders:
        query = query.where(Item.item_type == "file")

    result = await session.execute(query)
    items = result.scalars().all()

    target_values = normalize_metadata_values(request.target_values)
    to_change = 0
    already_compliant = 0
    sample_item_ids: list[str] = []
    has_organize_actions = request.apply_rename or request.apply_move

    for item in items:
        current = await session.scalar(
            select(ItemMetadata).where(
                ItemMetadata.account_id == item.account_id,
                ItemMetadata.item_id == item.item_id,
            )
        )
        current_values = normalize_metadata_values(current.values) if current else {}

        same_metadata = (
            current is not None
            and current.category_id == request.target_category_id
            and current_values == target_values
        )
        same = same_metadata and not has_organize_actions
        if same:
            already_compliant += 1
        else:
            to_change += 1
            if len(sample_item_ids) < max(1, request.limit):
                sample_item_ids.append(item.item_id)

    return MetadataRulePreviewResponse(
        total_matches=len(items),
        to_change=to_change,
        already_compliant=already_compliant,
        sample_item_ids=sample_item_ids,
    )


@router.get("/plugins", response_model=list[MetadataPluginSchema])
async def list_metadata_plugins(session: AsyncSession = Depends(get_session)):
    """List metadata plugins."""
    service = MetadataPluginService(session)
    plugins = await service.list_plugins()
    return plugins


@router.post("/plugins/{plugin_key}/activate", response_model=MetadataPluginSchema)
async def activate_metadata_plugin(plugin_key: str, session: AsyncSession = Depends(get_session)):
    """Activate a metadata plugin and ensure managed schema exists."""
    if plugin_key != COMIC_PLUGIN_KEY:
        raise HTTPException(status_code=404, detail="Unknown plugin")

    service = MetadataPluginService(session)
    try:
        plugin = await service.activate_comic_plugin()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OperationalError as exc:
        await session.rollback()
        if "no such table: metadata_plugins" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Database migration required: run alembic upgrade head") from exc
        raise

    await session.commit()
    await session.refresh(plugin)
    return plugin


@router.post("/plugins/{plugin_key}/deactivate", response_model=MetadataPluginSchema)
async def deactivate_metadata_plugin(plugin_key: str, session: AsyncSession = Depends(get_session)):
    """Deactivate a metadata plugin."""
    if plugin_key != COMIC_PLUGIN_KEY:
        raise HTTPException(status_code=404, detail="Unknown plugin")

    service = MetadataPluginService(session)
    try:
        plugin = await service.deactivate_comic_plugin()
    except OperationalError as exc:
        await session.rollback()
        if "no such table: metadata_plugins" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Database migration required: run alembic upgrade head") from exc
        raise
    await session.commit()
    await session.refresh(plugin)
    return plugin
