"""Helpers for metadata rule filtering."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backend.db.models import Item, ItemMetadata, MetadataAttribute

_EMPTY_OPERATORS = {"is_empty", "is_not_empty"}


def normalize_rule_filters(raw_filters: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_filters, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_filter in raw_filters:
        if hasattr(raw_filter, "model_dump"):
            raw_filter = raw_filter.model_dump(mode="json")
        if not isinstance(raw_filter, dict):
            continue
        source = str(raw_filter.get("source") or "metadata").strip().lower()
        if source not in {"metadata", "path"}:
            continue

        operator = str(raw_filter.get("operator") or "equals").strip().lower()
        attribute_id = raw_filter.get("attribute_id")
        if attribute_id is not None:
            attribute_id = str(attribute_id)

        normalized.append(
            {
                "source": source,
                "attribute_id": attribute_id,
                "operator": operator,
                "value": raw_filter.get("value"),
            }
        )
    return normalized


def item_matches_rule_filters(
    *,
    item: Item,
    metadata_row: ItemMetadata | None,
    target_category_id: UUID,
    filters: list[dict[str, Any]],
    attributes_by_id: dict[str, MetadataAttribute],
) -> bool:
    for rule_filter in normalize_rule_filters(filters):
        source = rule_filter["source"]
        operator = rule_filter["operator"]
        expected = rule_filter.get("value")
        if source == "path":
            candidate = item.path or ""
            if not _match_operator(candidate, operator, expected, data_type="text"):
                return False
            continue

        attr_id = str(rule_filter.get("attribute_id") or "").strip()
        attribute = attributes_by_id.get(attr_id)
        if attribute is None:
            return False

        candidate: Any = None
        if (
            metadata_row is not None
            and metadata_row.category_id == target_category_id
            and isinstance(metadata_row.values, dict)
        ):
            candidate = metadata_row.values.get(attr_id)

        if not _match_operator(
            candidate,
            operator,
            expected,
            data_type=attribute.data_type,
        ):
            return False

    return True


def _match_operator(
    candidate: Any,
    operator: str,
    expected: Any,
    *,
    data_type: str,
) -> bool:
    op = operator.strip().lower()
    if op in _EMPTY_OPERATORS:
        is_empty = _is_empty_value(candidate)
        return is_empty if op == "is_empty" else not is_empty

    if _is_empty_value(candidate):
        return False

    if data_type == "number":
        return _match_number(candidate, op, expected)
    if data_type == "boolean":
        return _match_boolean(candidate, op, expected)
    if data_type == "date":
        return _match_date(candidate, op, expected)
    if data_type == "tags":
        return _match_tags(candidate, op, expected)
    return _match_text(candidate, op, expected)


def _match_text(candidate: Any, operator: str, expected: Any) -> bool:
    left = str(candidate or "")
    right = str(expected or "")
    left_cmp = left.lower()
    right_cmp = right.lower()

    if operator == "equals":
        return left_cmp == right_cmp
    if operator == "not_equals":
        return left_cmp != right_cmp
    if operator == "contains":
        return right_cmp in left_cmp
    if operator == "not_contains":
        return right_cmp not in left_cmp
    if operator == "starts_with":
        return left_cmp.startswith(right_cmp)
    if operator == "ends_with":
        return left_cmp.endswith(right_cmp)
    return False


def _match_number(candidate: Any, operator: str, expected: Any) -> bool:
    try:
        left = float(candidate)
        right = float(expected)
    except (TypeError, ValueError):
        return False

    if operator == "equals":
        return left == right
    if operator == "not_equals":
        return left != right
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    return False


def _match_boolean(candidate: Any, operator: str, expected: Any) -> bool:
    left = _as_bool(candidate)
    right = _as_bool(expected)
    if left is None or right is None:
        return False
    if operator == "equals":
        return left is right
    if operator == "not_equals":
        return left is not right
    return False


def _match_date(candidate: Any, operator: str, expected: Any) -> bool:
    left = _as_datetime(candidate)
    right = _as_datetime(expected)
    if left is None or right is None:
        return _match_text(candidate, operator, expected)

    if operator == "equals":
        return left == right
    if operator == "not_equals":
        return left != right
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    return False


def _match_tags(candidate: Any, operator: str, expected: Any) -> bool:
    if not isinstance(candidate, list):
        return _match_text(candidate, operator, expected)

    normalized = [str(v).strip().lower() for v in candidate if str(v).strip()]
    target = str(expected or "").strip().lower()
    if operator == "contains":
        return target in normalized
    if operator == "not_contains":
        return target not in normalized
    if operator == "equals":
        return ",".join(normalized) == target
    if operator == "not_equals":
        return ",".join(normalized) != target
    return False


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len(value) == 0
    return False


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
