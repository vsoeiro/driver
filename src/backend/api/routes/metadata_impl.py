"""Metadata API routes."""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.dependencies import get_session
from backend.application.metadata.item_metadata_command_service import (
    ItemMetadataCommandService,
)
from backend.application.metadata.rules_service import MetadataRulesService
from backend.application.metadata.rule_preview_service import RulePreviewService
from backend.application.metadata.series_query_service import SeriesQueryService
from backend.db.models import (
    AppSetting,
    ItemMetadata,
    ItemMetadataHistory,
    MetadataAttribute,
    MetadataCategory,
)
from backend.domain.errors import NotFoundError
from backend.schemas.metadata import (
    ItemMetadata as ItemMetadataSchema,
)
from backend.schemas.metadata import (
    ItemMetadataCreate,
    ItemMetadataFieldUpdateRequest,
    MetadataAttributeCreate,
    MetadataAttributeUpdate,
    MetadataCategoryCreate,
    MetadataFormLayout,
    MetadataFormLayoutUpdate,
    MetadataRuleCreate,
    MetadataRulePreviewRequest,
    MetadataRulePreviewResponse,
    MetadataRuleUpdate,
    SeriesSummaryResponse,
)
from backend.schemas.metadata import (
    ItemMetadataHistory as ItemMetadataHistorySchema,
)
from backend.schemas.metadata import (
    MetadataAttribute as MetadataAttributeSchema,
)
from backend.schemas.metadata import (
    MetadataCategory as MetadataCategorySchema,
)
from backend.schemas.metadata import (
    MetadataLibrary as MetadataLibrarySchema,
)
from backend.schemas.metadata import (
    MetadataRule as MetadataRuleSchema,
)
from backend.services.metadata_libraries.service import (
    COMICS_LIBRARY_KEY,
    MetadataLibraryService,
)
from backend.services.metadata_versioning import (
    apply_metadata_change,
    normalize_metadata_values,
    undo_metadata_batch,
)

router = APIRouter(prefix="/metadata", tags=["Metadata"])
FORM_LAYOUTS_SETTING_KEY = "metadata_form_layouts_v1"

READ_ONLY_COMIC_FIELD_KEYS = {
    "cover_item_id",
    "cover_filename",
    "cover_account_id",
    "page_count",
    "file_format",
}


def _coerce_attribute_value(attribute: MetadataAttribute, raw_value: Any) -> Any:
    if raw_value is None:
        return None

    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if stripped == "":
            return None
    else:
        stripped = raw_value

    data_type = attribute.data_type

    if data_type == "text":
        return str(stripped)

    if data_type == "number":
        try:
            number = float(stripped)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid number for '{attribute.name}'"
            ) from exc
        if number.is_integer():
            return int(number)
        return number

    if data_type == "boolean":
        if isinstance(stripped, bool):
            return stripped
        if isinstance(stripped, (int, float)):
            return bool(stripped)
        normalized = str(stripped).strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise HTTPException(
            status_code=400, detail=f"Invalid boolean for '{attribute.name}'"
        )

    if data_type == "date":
        text = str(stripped).strip()
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date for '{attribute.name}' (use ISO format)",
            ) from exc
        return text

    if data_type == "select":
        options = (
            attribute.options.get("options")
            if isinstance(attribute.options, dict)
            else []
        )
        normalized_options = {str(opt).strip() for opt in options if str(opt).strip()}
        value = str(stripped).strip()
        if normalized_options and value not in normalized_options:
            raise HTTPException(
                status_code=400, detail=f"Invalid option for '{attribute.name}'"
            )
        return value

    if data_type == "tags":
        values: list[str] = []
        if isinstance(stripped, list):
            raw_values = stripped
        else:
            raw_values = str(stripped).split(",")
        seen: set[str] = set()
        for raw_entry in raw_values:
            candidate = str(raw_entry or "").strip()
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            values.append(candidate)
        return values or None

    return stripped


async def _reconcile_active_comic_schema(session: AsyncSession) -> None:
    service = MetadataLibraryService(session)
    libraries = await service.list_libraries()
    if any(
        library.key == COMICS_LIBRARY_KEY and library.is_active for library in libraries
    ):
        try:
            await service.ensure_active_comics_category()
            await session.commit()
        except ValueError:
            # Library flagged active but category is missing/inactive; keep request resilient.
            return


async def _load_form_layouts(session: AsyncSession) -> dict[str, dict]:
    row = await session.get(AppSetting, FORM_LAYOUTS_SETTING_KEY)
    if not row or not row.value:
        return {}
    import json

    try:
        parsed = json.loads(row.value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _save_form_layouts(session: AsyncSession, layouts: dict[str, dict]) -> None:
    import json

    row = await session.get(AppSetting, FORM_LAYOUTS_SETTING_KEY)
    serialized = json.dumps(layouts, ensure_ascii=True)
    if row is None:
        row = AppSetting(
            key=FORM_LAYOUTS_SETTING_KEY,
            value=serialized,
            description="Metadata form layouts by category",
        )
        session.add(row)
    else:
        row.value = serialized
        row.description = "Metadata form layouts by category"
    await session.commit()


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _region_is_free(occupied: set[tuple[int, int]], x: int, y: int, w: int) -> bool:
    for col in range(x, x + w):
        if (col, y) in occupied:
            return False
    return True


def _occupy_region(occupied: set[tuple[int, int]], x: int, y: int, w: int) -> None:
    for col in range(x, x + w):
        occupied.add((col, y))


def _find_first_free_slot(
    occupied: set[tuple[int, int]],
    columns: int,
    width: int,
    start_y: int = 0,
) -> tuple[int, int]:
    y = max(0, start_y)
    while y <= 10000:
        for x in range(0, max(1, columns - width + 1)):
            if _region_is_free(occupied, x, y, width):
                return x, y
        y += 1
    return 0, 0


def _layout_item_key(item: dict[str, Any]) -> str:
    item_type = str(item.get("item_type") or "attribute").lower()
    if item_type == "section":
        return f"section:{str(item.get('item_id') or '').strip()}"
    return f"attribute:{str(item.get('attribute_id') or '').strip()}"


def _parse_layout_items(raw_items: Any, columns: int) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        item_type = str(
            raw_item.get("item_type")
            or ("attribute" if raw_item.get("attribute_id") else "section")
        ).lower()

        if item_type == "section":
            raw_item_id = str(raw_item.get("item_id") or "").strip()
            item_id = raw_item_id or f"section_{index + 1}"
            key = f"section:{item_id}"
            if key in seen:
                continue
            seen.add(key)
            y = max(0, _to_int(raw_item.get("y"), 0))
            title = str(raw_item.get("title") or "").strip()
            items.append(
                {
                    "item_type": "section",
                    "item_id": item_id,
                    "attribute_id": None,
                    "title": title[:80] if title else None,
                    "x": 0,
                    "y": y,
                    "w": columns,
                    "h": 1,
                }
            )
            continue

        raw_attr_id = raw_item.get("attribute_id") or raw_item.get("item_id")
        try:
            attr_id = str(UUID(str(raw_attr_id)))
        except Exception:
            continue
        key = f"attribute:{attr_id}"
        if key in seen:
            continue
        seen.add(key)

        w = _clamp(_to_int(raw_item.get("w"), columns), 1, columns)
        x = _clamp(_to_int(raw_item.get("x"), 0), 0, columns - 1)
        if x + w > columns:
            x = max(0, columns - w)
        y = max(0, _to_int(raw_item.get("y"), 0))
        items.append(
            {
                "item_type": "attribute",
                "item_id": attr_id,
                "attribute_id": attr_id,
                "title": None,
                "x": x,
                "y": y,
                "w": w,
                "h": 1,
            }
        )
    return items


def _build_legacy_layout_items(
    raw_layout: dict[str, Any], columns: int
) -> list[dict[str, Any]]:
    ordered = []
    for raw_id in (raw_layout or {}).get("ordered_attribute_ids", []):
        try:
            ordered.append(str(UUID(str(raw_id))))
        except Exception:
            continue

    half_ids: set[str] = set()
    for raw_id in (raw_layout or {}).get("half_width_attribute_ids", []):
        try:
            half_ids.add(str(UUID(str(raw_id))))
        except Exception:
            continue

    items: list[dict[str, Any]] = []
    x = 0
    y = 0
    half_width = max(1, columns // 2)
    for attr_id in ordered:
        w = half_width if attr_id in half_ids else columns
        if x + w > columns:
            y += 1
            x = 0
        items.append(
            {
                "item_type": "attribute",
                "item_id": attr_id,
                "attribute_id": attr_id,
                "title": None,
                "x": x,
                "y": y,
                "w": w,
                "h": 1,
            }
        )
        if w >= columns:
            y += 1
            x = 0
        else:
            x += w
            if x >= columns:
                y += 1
                x = 0
    return items


def _normalize_layout_payload(
    raw_layout: dict[str, Any] | None,
    *,
    valid_attr_ids: set[str] | None = None,
    ordered_attr_ids: list[str] | None = None,
) -> dict[str, Any]:
    source = raw_layout or {}
    columns = _clamp(_to_int(source.get("columns"), 12), 1, 24)
    row_height = _clamp(_to_int(source.get("row_height"), 1), 1, 4)

    items = _parse_layout_items(source.get("items"), columns)
    if not items:
        items = _build_legacy_layout_items(source, columns)

    if valid_attr_ids is not None:
        filtered: list[dict[str, Any]] = []
        for item in items:
            if str(item.get("item_type") or "attribute") == "section":
                filtered.append(item)
                continue
            attr_id = str(item.get("attribute_id") or "")
            if attr_id in valid_attr_ids:
                filtered.append(item)
        items = filtered

    # Normalize occupancy to avoid overlaps and out-of-range placements.
    occupied: set[tuple[int, int]] = set()
    normalized_items: list[dict[str, Any]] = []
    sortable = sorted(
        items,
        key=lambda item: (_to_int(item.get("y"), 0), _to_int(item.get("x"), 0)),
    )
    seen_ids: set[str] = set()
    seen_item_keys: set[str] = set()
    for item in sortable:
        item_type = str(item.get("item_type") or "attribute").lower()
        item_key = _layout_item_key(item)
        if item_key in seen_item_keys:
            continue
        seen_item_keys.add(item_key)

        if item_type == "section":
            section_id = str(item.get("item_id") or "").strip()
            if not section_id:
                section_id = f"section_{len(seen_item_keys)}"
            w = columns
            x = 0
            y = max(0, _to_int(item.get("y"), 0))
            if not _region_is_free(occupied, x, y, w):
                x, y = _find_first_free_slot(occupied, columns, w, y)
            _occupy_region(occupied, x, y, w)
            title = str(item.get("title") or "").strip()
            normalized_items.append(
                {
                    "item_type": "section",
                    "item_id": section_id,
                    "attribute_id": None,
                    "title": title[:80] if title else None,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": 1,
                }
            )
            continue

        attr_id = str(item.get("attribute_id") or "")
        if not attr_id:
            continue
        seen_ids.add(attr_id)
        w = _clamp(_to_int(item.get("w"), columns), 1, columns)
        x = _clamp(_to_int(item.get("x"), 0), 0, columns - 1)
        if x + w > columns:
            x = max(0, columns - w)
        y = max(0, _to_int(item.get("y"), 0))
        if not _region_is_free(occupied, x, y, w):
            x, y = _find_first_free_slot(occupied, columns, w, y)
        _occupy_region(occupied, x, y, w)
        normalized_items.append(
            {
                "item_type": "attribute",
                "item_id": attr_id,
                "attribute_id": attr_id,
                "title": None,
                "x": x,
                "y": y,
                "w": w,
                "h": 1,
            }
        )

    # Ensure every attribute has a layout position.
    if ordered_attr_ids:
        for attr_id in ordered_attr_ids:
            if valid_attr_ids is not None and attr_id not in valid_attr_ids:
                continue
            if attr_id in seen_ids:
                continue
            x, y = _find_first_free_slot(occupied, columns, columns, 0)
            _occupy_region(occupied, x, y, columns)
            normalized_items.append(
                {
                    "item_type": "attribute",
                    "item_id": attr_id,
                    "attribute_id": attr_id,
                    "title": None,
                    "x": x,
                    "y": y,
                    "w": columns,
                    "h": 1,
                }
            )
            seen_ids.add(attr_id)

    normalized_items.sort(
        key=lambda item: (_to_int(item.get("y"), 0), _to_int(item.get("x"), 0))
    )
    ordered_ids = [
        str(item["attribute_id"])
        for item in normalized_items
        if str(item.get("item_type") or "attribute") == "attribute"
        and item.get("attribute_id")
    ]
    half_ids = [
        str(item["attribute_id"])
        for item in normalized_items
        if str(item.get("item_type") or "attribute") == "attribute"
        and item.get("attribute_id")
        and _to_int(item.get("w"), columns) <= max(1, columns // 2)
    ]

    return {
        "columns": columns,
        "row_height": row_height,
        "items": normalized_items,
        "ordered_attribute_ids": ordered_ids,
        "half_width_attribute_ids": half_ids,
    }


def _to_form_layout_response(
    category_id: UUID, raw_layout: dict[str, Any]
) -> MetadataFormLayout:
    normalized = _normalize_layout_payload(raw_layout)
    items_payload = []
    for item in normalized["items"]:
        try:
            item_type = str(item.get("item_type") or "attribute")
            item_id = str(item.get("item_id") or "").strip()
            raw_attr_id = item.get("attribute_id")
            attr_uuid = None
            if raw_attr_id:
                attr_uuid = UUID(str(raw_attr_id))
            items_payload.append(
                {
                    "item_type": item_type,
                    "item_id": item_id or (str(attr_uuid) if attr_uuid else None),
                    "attribute_id": attr_uuid,
                    "title": item.get("title"),
                    "x": int(item["x"]),
                    "y": int(item["y"]),
                    "w": int(item["w"]),
                    "h": int(item.get("h", 1)),
                }
            )
        except Exception:
            continue

    ordered_ids = []
    for raw_id in normalized["ordered_attribute_ids"]:
        try:
            ordered_ids.append(UUID(str(raw_id)))
        except Exception:
            continue
    half_ids = []
    for raw_id in normalized["half_width_attribute_ids"]:
        try:
            half_ids.append(UUID(str(raw_id)))
        except Exception:
            continue

    return MetadataFormLayout(
        category_id=category_id,
        columns=int(normalized["columns"]),
        row_height=int(normalized["row_height"]),
        items=items_payload,
        ordered_attribute_ids=ordered_ids,
        half_width_attribute_ids=half_ids,
    )


def _can_inline_edit_attribute(attribute: MetadataAttribute) -> bool:
    # Comics library fields are editable except technical read-only keys.
    if attribute.plugin_key == COMICS_LIBRARY_KEY:
        return (attribute.plugin_field_key or "") not in READ_ONLY_COMIC_FIELD_KEYS
    # Non-library attributes follow lock rules.
    return not (attribute.is_locked or attribute.managed_by_plugin)


async def _validate_rule_configuration(session: AsyncSession, payload: dict) -> None:
    await MetadataRulesService(session).validate_rule_configuration(payload)


# --- Categories ---
@router.get("/categories", response_model=list[MetadataCategorySchema])
async def list_categories(session: AsyncSession = Depends(get_session)):
    """List all metadata categories with their attributes."""
    await _reconcile_active_comic_schema(session)
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
    await _reconcile_active_comic_schema(session)
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


@router.get("/layouts", response_model=list[MetadataFormLayout])
async def list_metadata_form_layouts(session: AsyncSession = Depends(get_session)):
    layouts = await _load_form_layouts(session)
    result: list[MetadataFormLayout] = []
    for category_id, raw in layouts.items():
        try:
            cid = UUID(str(category_id))
        except Exception:
            continue
        result.append(
            _to_form_layout_response(cid, raw if isinstance(raw, dict) else {})
        )
    return result


@router.get("/layouts/{category_id}", response_model=MetadataFormLayout)
async def get_metadata_form_layout(
    category_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    attrs_stmt = (
        select(MetadataAttribute.id)
        .where(MetadataAttribute.category_id == category_id)
        .order_by(MetadataAttribute.name.asc(), MetadataAttribute.id.asc())
    )
    category_attr_ids = [
        str(attr_id) for attr_id in (await session.execute(attrs_stmt)).scalars().all()
    ]

    layouts = await _load_form_layouts(session)
    raw_layout = layouts.get(str(category_id), {})
    normalized = _normalize_layout_payload(
        raw_layout if isinstance(raw_layout, dict) else {},
        valid_attr_ids=set(category_attr_ids),
        ordered_attr_ids=category_attr_ids,
    )
    return _to_form_layout_response(category_id, normalized)


@router.put("/layouts/{category_id}", response_model=MetadataFormLayout)
async def upsert_metadata_form_layout(
    category_id: UUID,
    payload: MetadataFormLayoutUpdate,
    session: AsyncSession = Depends(get_session),
):
    category = await session.get(MetadataCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    attrs_stmt = (
        select(MetadataAttribute.id)
        .where(MetadataAttribute.category_id == category_id)
        .order_by(MetadataAttribute.name.asc(), MetadataAttribute.id.asc())
    )
    attr_ids_ordered = [
        str(attr_id) for attr_id in (await session.execute(attrs_stmt)).scalars().all()
    ]
    attr_ids = set(attr_ids_ordered)

    raw_payload = payload.model_dump(mode="json")
    # Backward compatibility: if caller sends only ordered/half arrays, build legacy item layout.
    if not raw_payload.get("items"):
        raw_payload["items"] = []
    if not raw_payload.get("ordered_attribute_ids"):
        raw_payload["ordered_attribute_ids"] = [
            str(attr_id) for attr_id in payload.ordered_attribute_ids
        ]
    if not raw_payload.get("half_width_attribute_ids"):
        raw_payload["half_width_attribute_ids"] = [
            str(attr_id) for attr_id in payload.half_width_attribute_ids
        ]

    normalized = _normalize_layout_payload(
        raw_payload,
        valid_attr_ids=attr_ids,
        ordered_attr_ids=attr_ids_ordered,
    )

    layouts = await _load_form_layouts(session)
    layouts[str(category_id)] = {
        "columns": normalized["columns"],
        "row_height": normalized["row_height"],
        "items": normalized["items"],
        "ordered_attribute_ids": normalized["ordered_attribute_ids"],
        "half_width_attribute_ids": normalized["half_width_attribute_ids"],
    }
    await _save_form_layouts(session, layouts)

    return _to_form_layout_response(category_id, normalized)


@router.get(
    "/categories/{category_id}/series-summary", response_model=SeriesSummaryResponse
)
async def get_category_series_summary(
    category_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    sort_by: str = Query("series", pattern="^(series|total_items)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    q: str | None = None,
    search_fields: str = Query("both", pattern="^(name|path|both)$"),
    account_id: UUID | None = None,
    item_type: str | None = Query(None, pattern="^(file|folder)$"),
    metadata_filters: str | None = Query(None, alias="metadata"),
    session: AsyncSession = Depends(get_session),
):
    """Return one-page summary grouped by comic series for Series view."""
    service = SeriesQueryService(session)
    try:
        return await service.get_category_series_summary(
            category_id=category_id,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            q=q,
            search_fields=search_fields,
            account_id=account_id,
            item_type=item_type,
            metadata_filters=metadata_filters,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.post(
    "/categories",
    response_model=MetadataCategorySchema,
    status_code=status.HTTP_201_CREATED,
)
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
async def delete_category(
    category_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Delete a metadata category."""
    category = await session.get(MetadataCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.is_locked or category.managed_by_plugin:
        raise HTTPException(
            status_code=400,
            detail="Library-managed category cannot be deleted. Deactivate the metadata library instead.",
        )

    # Remove metadata assignments that reference this category.
    # `item_metadata.category_id` is not a FK, so this cleanup is manual.
    await session.execute(
        delete(ItemMetadata).where(ItemMetadata.category_id == category_id)
    )
    await session.delete(category)
    await session.commit()


# --- Attributes ---
@router.post(
    "/categories/{category_id}/attributes",
    response_model=MetadataAttributeSchema,
    status_code=status.HTTP_201_CREATED,
)
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
        raise HTTPException(
            status_code=400, detail="Cannot add attributes to an inactive category"
        )

    db_attribute = MetadataAttribute(category_id=category_id, **attribute.model_dump())
    session.add(db_attribute)
    await session.commit()
    await session.refresh(db_attribute)
    return db_attribute


@router.delete("/attributes/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attribute(
    attribute_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Delete a metadata attribute."""
    attribute = await session.get(MetadataAttribute, attribute_id)
    if not attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")
    if attribute.is_locked or attribute.managed_by_plugin:
        raise HTTPException(
            status_code=400, detail="Library-managed attribute cannot be deleted"
        )

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
        raise HTTPException(
            status_code=400, detail="Library-managed attribute cannot be edited"
        )

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


@router.patch(
    "/items/{account_id}/{item_id}/attributes/{attribute_id}",
    response_model=ItemMetadataSchema,
)
async def update_item_metadata_attribute(
    account_id: UUID,
    item_id: str,
    attribute_id: UUID,
    payload: ItemMetadataFieldUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update one metadata attribute value for one item."""
    attribute = await session.get(MetadataAttribute, attribute_id)
    if not attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")
    if not _can_inline_edit_attribute(attribute):
        raise HTTPException(
            status_code=400, detail="Attribute is locked and cannot be edited"
        )

    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id,
    )
    existing_row = await session.execute(stmt)
    existing = existing_row.scalar_one_or_none()

    if (
        payload.expected_version is not None
        and existing
        and existing.version != payload.expected_version
    ):
        raise HTTPException(
            status_code=409,
            detail="Metadata was updated by another process. Refresh and try again.",
        )

    target_category_id = existing.category_id if existing else payload.category_id
    if target_category_id is None:
        target_category_id = attribute.category_id

    if target_category_id != attribute.category_id:
        raise HTTPException(
            status_code=400, detail="Attribute does not belong to the selected category"
        )

    coerced_value = _coerce_attribute_value(attribute, payload.value)
    merged_values = normalize_metadata_values(existing.values if existing else {})
    attr_key = str(attribute_id)
    if coerced_value is None:
        merged_values.pop(attr_key, None)
    else:
        merged_values[attr_key] = coerced_value

    await apply_metadata_change(
        session,
        account_id=account_id,
        item_id=item_id,
        category_id=target_category_id,
        values=merged_values,
    )
    await session.commit()

    refreshed = await session.execute(stmt)
    updated = refreshed.scalar_one_or_none()
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to save metadata")
    return updated


@router.post("/items", response_model=ItemMetadataSchema)
async def upsert_item_metadata(
    metadata: ItemMetadataCreate, session: AsyncSession = Depends(get_session)
):
    """Assign or update metadata for an item."""
    service = ItemMetadataCommandService(session)
    return await service.upsert_item_metadata(metadata)


@router.delete("/items/{account_id}/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_metadata(
    account_id: UUID, item_id: str, session: AsyncSession = Depends(get_session)
):
    """Remove metadata from an item."""
    query = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id, ItemMetadata.item_id == item_id
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
    account_id: UUID, item_ids: list[str], session: AsyncSession = Depends(get_session)
):
    """Remove metadata for multiple items."""
    query = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id, ItemMetadata.item_id.in_(item_ids)
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
    return await MetadataRulesService(session).list_rules()


@router.post(
    "/rules", response_model=MetadataRuleSchema, status_code=status.HTTP_201_CREATED
)
async def create_metadata_rule(
    rule: MetadataRuleCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a metadata rule."""
    return await MetadataRulesService(session).create_rule(rule)


@router.patch("/rules/{rule_id}", response_model=MetadataRuleSchema)
async def update_metadata_rule(
    rule_id: UUID,
    rule: MetadataRuleUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a metadata rule."""
    return await MetadataRulesService(session).update_rule(rule_id=rule_id, payload=rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metadata_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete a metadata rule."""
    await MetadataRulesService(session).delete_rule(rule_id)


@router.post("/rules/preview", response_model=MetadataRulePreviewResponse)
async def preview_metadata_rule(
    request: MetadataRulePreviewRequest,
    session: AsyncSession = Depends(get_session),
):
    """Preview how many items would be changed by a rule."""
    await _validate_rule_configuration(session, request.model_dump())
    service = RulePreviewService(session)
    return await service.preview(request)


@router.get("/libraries", response_model=list[MetadataLibrarySchema])
async def list_metadata_libraries(session: AsyncSession = Depends(get_session)):
    """List metadata libraries."""
    service = MetadataLibraryService(session)
    libraries = await service.list_libraries()
    return libraries


@router.post("/libraries/{library_key}/activate", response_model=MetadataLibrarySchema)
async def activate_metadata_library(
    library_key: str, session: AsyncSession = Depends(get_session)
):
    """Activate a metadata library and ensure managed schema exists."""
    if library_key != COMICS_LIBRARY_KEY:
        raise HTTPException(status_code=404, detail="Unknown metadata library")

    service = MetadataLibraryService(session)
    try:
        library = await service.activate_comics_library()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OperationalError as exc:
        await session.rollback()
        if "no such table: metadata_plugins" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail="Database migration required: run alembic upgrade head",
            ) from exc
        raise

    await session.commit()
    await session.refresh(library)
    return library


@router.post(
    "/libraries/{library_key}/deactivate", response_model=MetadataLibrarySchema
)
async def deactivate_metadata_library(
    library_key: str, session: AsyncSession = Depends(get_session)
):
    """Deactivate a metadata library."""
    if library_key != COMICS_LIBRARY_KEY:
        raise HTTPException(status_code=404, detail="Unknown metadata library")

    service = MetadataLibraryService(session)
    try:
        library = await service.deactivate_comics_library()
    except OperationalError as exc:
        await session.rollback()
        if "no such table: metadata_plugins" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail="Database migration required: run alembic upgrade head",
            ) from exc
        raise
    await session.commit()
    await session.refresh(library)
    return library
