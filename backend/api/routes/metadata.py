"""Metadata API routes."""

import uuid
from uuid import UUID
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import OperationalError
from sqlalchemy import select, func, delete, cast, Float, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.dependencies import get_session
from backend.db.models import (
    AppSetting,
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
    ItemMetadataFieldUpdateRequest,
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
    MetadataFormLayout,
    MetadataFormLayoutUpdate,
    SeriesSummaryResponse,
)
from backend.services.metadata_plugins import COMIC_PLUGIN_KEY, MetadataPluginService
from backend.services.metadata_versioning import apply_metadata_change, normalize_metadata_values, undo_metadata_batch
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager

router = APIRouter(prefix="/metadata", tags=["Metadata"])
FORM_LAYOUTS_SETTING_KEY = "metadata_form_layouts_v1"

READ_ONLY_COMIC_FIELD_KEYS = {
    "cover_item_id",
    "cover_filename",
    "cover_account_id",
    "page_count",
    "file_format",
}


def _build_metadata_filter_conditions(filters: dict) -> list:
    conditions = []
    for attr_id, raw_filter in (filters or {}).items():
        if not attr_id:
            continue

        field_text = func.coalesce(
            ItemMetadata.values[attr_id].as_string(),
            cast(ItemMetadata.values[attr_id], String),
        )
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


def _parse_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = int(float(text))
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


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
            raise HTTPException(status_code=400, detail=f"Invalid number for '{attribute.name}'") from exc
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
        raise HTTPException(status_code=400, detail=f"Invalid boolean for '{attribute.name}'")

    if data_type == "date":
        text = str(stripped).strip()
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date for '{attribute.name}' (use ISO format)") from exc
        return text

    if data_type == "select":
        options = attribute.options.get("options") if isinstance(attribute.options, dict) else []
        normalized_options = {str(opt).strip() for opt in options if str(opt).strip()}
        value = str(stripped).strip()
        if normalized_options and value not in normalized_options:
            raise HTTPException(status_code=400, detail=f"Invalid option for '{attribute.name}'")
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
    service = MetadataPluginService(session)
    plugins = await service.list_plugins()
    if any(plugin.key == COMIC_PLUGIN_KEY and plugin.is_active for plugin in plugins):
        try:
            await service.ensure_active_comic_category()
            await session.commit()
        except ValueError:
            # Plugin flagged active but category is missing/inactive; keep request resilient.
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
        item_type = str(raw_item.get("item_type") or ("attribute" if raw_item.get("attribute_id") else "section")).lower()

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


def _build_legacy_layout_items(raw_layout: dict[str, Any], columns: int) -> list[dict[str, Any]]:
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

    normalized_items.sort(key=lambda item: (_to_int(item.get("y"), 0), _to_int(item.get("x"), 0)))
    ordered_ids = [
        str(item["attribute_id"])
        for item in normalized_items
        if str(item.get("item_type") or "attribute") == "attribute" and item.get("attribute_id")
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


def _to_form_layout_response(category_id: UUID, raw_layout: dict[str, Any]) -> MetadataFormLayout:
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
    # Comic plugin fields are editable except technical read-only keys.
    if attribute.plugin_key == COMIC_PLUGIN_KEY:
        return (attribute.plugin_field_key or "") not in READ_ONLY_COMIC_FIELD_KEYS
    # Non-plugin attributes follow lock rules.
    return not (attribute.is_locked or attribute.managed_by_plugin)


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
        result.append(_to_form_layout_response(cid, raw if isinstance(raw, dict) else {}))
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
    category_attr_ids = [str(attr_id) for attr_id in (await session.execute(attrs_stmt)).scalars().all()]

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
    attr_ids_ordered = [str(attr_id) for attr_id in (await session.execute(attrs_stmt)).scalars().all()]
    attr_ids = set(attr_ids_ordered)

    raw_payload = payload.model_dump(mode="json")
    # Backward compatibility: if caller sends only ordered/half arrays, build legacy item layout.
    if not raw_payload.get("items"):
        raw_payload["items"] = []
    if not raw_payload.get("ordered_attribute_ids"):
        raw_payload["ordered_attribute_ids"] = [str(attr_id) for attr_id in payload.ordered_attribute_ids]
    if not raw_payload.get("half_width_attribute_ids"):
        raw_payload["half_width_attribute_ids"] = [str(attr_id) for attr_id in payload.half_width_attribute_ids]

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


@router.get("/categories/{category_id}/series-summary", response_model=SeriesSummaryResponse)
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
    category_query = (
        select(MetadataCategory)
        .where(MetadataCategory.id == category_id)
        .options(selectinload(MetadataCategory.attributes))
    )
    category_result = await session.execute(category_query)
    category = category_result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    attr_by_plugin_key = {
        (attr.plugin_field_key or "").strip().lower(): str(attr.id)
        for attr in category.attributes
        if attr.plugin_field_key
    }
    attr_by_name = {
        (attr.name or "").strip().lower(): str(attr.id)
        for attr in category.attributes
        if attr.name
    }

    series_attr_id = attr_by_plugin_key.get("series") or attr_by_name.get("series")
    if not series_attr_id:
        return SeriesSummaryResponse(rows=[], total=0, page=page, page_size=page_size, total_pages=0)

    volume_attr_id = attr_by_plugin_key.get("volume") or attr_by_name.get("volume")
    issue_attr_id = attr_by_plugin_key.get("issue_number") or attr_by_name.get("issue number")
    max_volumes_attr_id = attr_by_plugin_key.get("max_volumes") or attr_by_name.get("max volumes")
    max_issues_attr_id = attr_by_plugin_key.get("max_issues") or attr_by_name.get("max issues")
    status_attr_id = attr_by_plugin_key.get("series_status") or attr_by_name.get("series status")

    series_text_expr = func.trim(ItemMetadata.values[series_attr_id].as_string())
    series_key_expr = func.lower(series_text_expr)
    conditions = [
        ItemMetadata.category_id == category_id,
        series_text_expr.isnot(None),
        series_text_expr != "",
        ItemMetadata.account_id == Item.account_id,
        ItemMetadata.item_id == Item.item_id,
    ]

    if account_id:
        conditions.append(Item.account_id == account_id)
    if item_type:
        conditions.append(Item.item_type == item_type)
    if q:
        search_pattern = f"%{q}%"
        if search_fields == "name":
            conditions.append(Item.name.ilike(search_pattern))
        elif search_fields == "path":
            conditions.append(Item.path.ilike(search_pattern))
        else:
            conditions.append(Item.name.ilike(search_pattern) | Item.path.ilike(search_pattern))

    if metadata_filters:
        import json
        try:
            parsed_filters = json.loads(metadata_filters)
            conditions.extend(_build_metadata_filter_conditions(parsed_filters))
        except Exception:
            pass

    count_stmt = (
        select(func.count(func.distinct(series_key_expr)))
        .select_from(ItemMetadata, Item)
        .where(*conditions)
    )
    total = int((await session.execute(count_stmt)).scalar_one() or 0)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    if total == 0:
        return SeriesSummaryResponse(rows=[], total=0, page=page, page_size=page_size, total_pages=0)

    series_name_agg = func.min(series_text_expr)
    total_items_agg = func.count(ItemMetadata.id)
    series_rows_stmt = (
        select(
            series_key_expr.label("series_key"),
            series_name_agg.label("series_name"),
            total_items_agg.label("total_items"),
        )
        .select_from(ItemMetadata, Item)
        .where(*conditions)
        .group_by(series_key_expr)
    )
    if sort_by == "total_items":
        series_rows_stmt = series_rows_stmt.order_by(
            total_items_agg.desc() if sort_order == "desc" else total_items_agg.asc(),
            series_name_agg.asc(),
        )
    else:
        series_rows_stmt = series_rows_stmt.order_by(
            series_name_agg.desc() if sort_order == "desc" else series_name_agg.asc()
        )

    series_rows_stmt = series_rows_stmt.offset((page - 1) * page_size).limit(page_size)
    series_rows_result = await session.execute(series_rows_stmt)
    series_rows = series_rows_result.all()
    if not series_rows:
        return SeriesSummaryResponse(rows=[], total=total, page=page, page_size=page_size, total_pages=total_pages)

    page_series_keys = [row.series_key for row in series_rows]
    by_key = {
        row.series_key: {
            "series_name": (row.series_name or "").strip() or "Unknown",
            "total_items": int(row.total_items or 0),
            "owned_volumes": set(),
            "issues_by_volume": {},
            "max_volumes_candidates": [],
            "max_issues_candidates": [],
            "status_votes": {},
        }
        for row in series_rows
    }

    if volume_attr_id:
        volume_expr = func.trim(ItemMetadata.values[volume_attr_id].as_string())
        volume_stmt = (
            select(series_key_expr.label("series_key"), volume_expr.label("volume_text"))
            .select_from(ItemMetadata, Item)
            .where(*conditions, series_key_expr.in_(page_series_keys), volume_expr.isnot(None), volume_expr != "")
            .group_by(series_key_expr, volume_expr)
        )
        for row in (await session.execute(volume_stmt)).all():
            parsed_volume = _parse_positive_int(row.volume_text)
            if parsed_volume:
                by_key[row.series_key]["owned_volumes"].add(parsed_volume)

    if volume_attr_id and issue_attr_id:
        volume_expr = func.trim(ItemMetadata.values[volume_attr_id].as_string())
        issue_expr = func.trim(ItemMetadata.values[issue_attr_id].as_string())
        issue_stmt = (
            select(
                series_key_expr.label("series_key"),
                volume_expr.label("volume_text"),
                issue_expr.label("issue_text"),
            )
            .select_from(ItemMetadata, Item)
            .where(
                *conditions,
                series_key_expr.in_(page_series_keys),
                volume_expr.isnot(None),
                volume_expr != "",
                issue_expr.isnot(None),
                issue_expr != "",
            )
            .group_by(series_key_expr, volume_expr, issue_expr)
        )
        for row in (await session.execute(issue_stmt)).all():
            parsed_volume = _parse_positive_int(row.volume_text)
            parsed_issue = _parse_positive_int(row.issue_text)
            if not parsed_volume or not parsed_issue:
                continue
            volume_bucket = by_key[row.series_key]["issues_by_volume"].setdefault(parsed_volume, set())
            volume_bucket.add(parsed_issue)

    if max_volumes_attr_id:
        max_volumes_expr = func.trim(ItemMetadata.values[max_volumes_attr_id].as_string())
        max_volumes_stmt = (
            select(series_key_expr.label("series_key"), max_volumes_expr.label("max_volumes_text"))
            .select_from(ItemMetadata, Item)
            .where(
                *conditions,
                series_key_expr.in_(page_series_keys),
                max_volumes_expr.isnot(None),
                max_volumes_expr != "",
            )
            .group_by(series_key_expr, max_volumes_expr)
        )
        for row in (await session.execute(max_volumes_stmt)).all():
            parsed_value = _parse_positive_int(row.max_volumes_text)
            if parsed_value:
                by_key[row.series_key]["max_volumes_candidates"].append(parsed_value)

    if max_issues_attr_id:
        max_issues_expr = func.trim(ItemMetadata.values[max_issues_attr_id].as_string())
        max_issues_stmt = (
            select(series_key_expr.label("series_key"), max_issues_expr.label("max_issues_text"))
            .select_from(ItemMetadata, Item)
            .where(
                *conditions,
                series_key_expr.in_(page_series_keys),
                max_issues_expr.isnot(None),
                max_issues_expr != "",
            )
            .group_by(series_key_expr, max_issues_expr)
        )
        for row in (await session.execute(max_issues_stmt)).all():
            parsed_value = _parse_positive_int(row.max_issues_text)
            if parsed_value:
                by_key[row.series_key]["max_issues_candidates"].append(parsed_value)

    if status_attr_id:
        status_expr = func.lower(func.trim(ItemMetadata.values[status_attr_id].as_string()))
        status_stmt = (
            select(
                series_key_expr.label("series_key"),
                status_expr.label("series_status"),
                func.count(ItemMetadata.id).label("status_count"),
            )
            .select_from(ItemMetadata, Item)
            .where(
                *conditions,
                series_key_expr.in_(page_series_keys),
                status_expr.isnot(None),
                status_expr != "",
            )
            .group_by(series_key_expr, status_expr)
        )
        for row in (await session.execute(status_stmt)).all():
            by_key[row.series_key]["status_votes"][row.series_status] = int(row.status_count or 0)

    rows = []
    for series_key in page_series_keys:
        row = by_key.get(series_key)
        if not row:
            continue

        owned_volumes = sorted(row["owned_volumes"])
        owned_volume_max = max(owned_volumes) if owned_volumes else 0
        declared_max_volumes = max(row["max_volumes_candidates"]) if row["max_volumes_candidates"] else 0
        max_volumes = max(owned_volume_max, declared_max_volumes)
        max_issues = max(row["max_issues_candidates"]) if row["max_issues_candidates"] else 0

        status_votes = row["status_votes"]
        if status_votes:
            series_status = max(status_votes.items(), key=lambda item: item[1])[0]
        else:
            series_status = "unknown"

        issues_by_volume = {
            str(volume): sorted(issue_set)
            for volume, issue_set in row["issues_by_volume"].items()
        }
        rows.append(
            {
                "series_name": row["series_name"],
                "total_items": row["total_items"],
                "owned_volumes": owned_volumes,
                "issues_by_volume": issues_by_volume,
                "max_volumes": max_volumes,
                "max_issues": max_issues,
                "series_status": series_status,
            }
        )

    return SeriesSummaryResponse(
        rows=rows,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


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
        raise HTTPException(status_code=400, detail="Attribute is locked and cannot be edited")

    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_id,
        ItemMetadata.item_id == item_id,
    )
    existing_row = await session.execute(stmt)
    existing = existing_row.scalar_one_or_none()

    if payload.expected_version is not None and existing and existing.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Metadata was updated by another process. Refresh and try again.")

    target_category_id = existing.category_id if existing else payload.category_id
    if target_category_id is None:
        target_category_id = attribute.category_id

    if target_category_id != attribute.category_id:
        raise HTTPException(status_code=400, detail="Attribute does not belong to the selected category")

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
