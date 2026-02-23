import sqlalchemy as sa

from backend.common.metadata_filters import build_metadata_filter_conditions


VALUES_COLUMN = sa.table(
    "item_metadata",
    sa.column("values", sa.JSON),
).c["values"]


def _build(op: str, value: object) -> list:
    return build_metadata_filter_conditions(
        {"attr-1": {"op": op, "value": value}},
        VALUES_COLUMN,
    )


def test_build_metadata_filter_conditions_supports_string_ops():
    for operator in ("eq", "ne", "contains", "not_contains", "starts_with", "ends_with"):
        conditions = _build(operator, "abc")
        assert len(conditions) == 1


def test_build_metadata_filter_conditions_supports_numeric_ops():
    for operator in ("gt", "gte", "lt", "lte"):
        conditions = _build(operator, "10")
        assert len(conditions) == 1


def test_build_metadata_filter_conditions_supports_min_max_range():
    conditions = build_metadata_filter_conditions(
        {"attr-1": {"min": "1", "max": "9"}},
        VALUES_COLUMN,
    )
    assert len(conditions) == 2


def test_build_metadata_filter_conditions_ignores_invalid_numeric_values():
    conditions = _build("gt", "not-a-number")
    assert conditions == []
