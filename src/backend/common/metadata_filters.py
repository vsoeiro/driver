"""Shared SQL builders for metadata JSON filtering."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, String, cast, func


def build_metadata_filter_conditions(filters: dict[str, Any] | None, values_column: Any) -> list[Any]:
    """Convert metadata filter payload into SQLAlchemy conditions."""
    conditions: list[Any] = []
    for attr_id, raw_filter in (filters or {}).items():
        if not attr_id:
            continue

        field_text = func.coalesce(
            values_column[attr_id].as_string(),
            cast(values_column[attr_id], String),
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

