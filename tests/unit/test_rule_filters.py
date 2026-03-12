from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from backend.application.metadata.rule_filters import (
    item_matches_rule_filters,
    normalize_rule_filters,
)
from backend.schemas.metadata import MetadataRuleFilter


def test_normalize_rule_filters_accepts_pydantic_models():
    filters = [
        MetadataRuleFilter(
            source="metadata",
            attribute_id=UUID("84a84dc1-d83a-4b84-a6bb-96c934c9f662"),
            operator="equals",
            value="Monstress",
        )
    ]

    assert normalize_rule_filters(filters) == [
        {
            "source": "metadata",
            "attribute_id": "84a84dc1-d83a-4b84-a6bb-96c934c9f662",
            "operator": "equals",
            "value": "Monstress",
        }
    ]


def test_normalize_rule_filters_discards_invalid_entries():
    assert normalize_rule_filters(
        [
            None,
            "invalid",
            {"source": "unsupported", "operator": "equals", "value": "x"},
            {"source": "path", "operator": "contains", "value": "Books"},
        ]
    ) == [
        {
            "source": "path",
            "attribute_id": None,
            "operator": "contains",
            "value": "Books",
        }
    ]


def test_item_matches_rule_filters_supports_path_and_typed_metadata_filters():
    target_category_id = uuid4()
    text_attr = str(uuid4())
    number_attr = str(uuid4())
    bool_attr = str(uuid4())
    date_attr = str(uuid4())
    tags_attr = str(uuid4())

    item = SimpleNamespace(
        account_id=uuid4(),
        item_id="item-1",
        path="/Library/Saga/issue-01.cbz",
    )
    metadata_row = SimpleNamespace(
        category_id=target_category_id,
        values={
            text_attr: "Saga",
            number_attr: "7",
            bool_attr: "true",
            date_attr: datetime(2026, 3, 10, tzinfo=timezone.utc).isoformat(),
            tags_attr: ["Sci-Fi", "Epic"],
        },
    )
    attributes_by_id = {
        text_attr: SimpleNamespace(data_type="text"),
        number_attr: SimpleNamespace(data_type="number"),
        bool_attr: SimpleNamespace(data_type="boolean"),
        date_attr: SimpleNamespace(data_type="date"),
        tags_attr: SimpleNamespace(data_type="tags"),
    }

    assert item_matches_rule_filters(
        item=item,
        metadata_row=metadata_row,
        target_category_id=target_category_id,
        filters=[
            {"source": "path", "operator": "contains", "value": "saga"},
            {"source": "metadata", "attribute_id": text_attr, "operator": "starts_with", "value": "sa"},
            {"source": "metadata", "attribute_id": number_attr, "operator": "gte", "value": 6},
            {"source": "metadata", "attribute_id": bool_attr, "operator": "equals", "value": True},
            {
                "source": "metadata",
                "attribute_id": date_attr,
                "operator": "lte",
                "value": datetime(2026, 3, 10, tzinfo=timezone.utc).isoformat(),
            },
            {"source": "metadata", "attribute_id": tags_attr, "operator": "contains", "value": "epic"},
        ],
        attributes_by_id=attributes_by_id,
    )


def test_item_matches_rule_filters_handles_empty_values_and_missing_attributes():
    item = SimpleNamespace(account_id=uuid4(), item_id="item-1", path="/Library/Saga")
    target_category_id = uuid4()
    attr_id = str(uuid4())
    metadata_row = SimpleNamespace(
        category_id=uuid4(),
        values={attr_id: "Saga"},
    )
    attributes_by_id = {
        attr_id: SimpleNamespace(data_type="text"),
    }

    assert item_matches_rule_filters(
        item=item,
        metadata_row=metadata_row,
        target_category_id=target_category_id,
        filters=[{"source": "metadata", "attribute_id": attr_id, "operator": "is_empty"}],
        attributes_by_id=attributes_by_id,
    )
    assert not item_matches_rule_filters(
        item=item,
        metadata_row=metadata_row,
        target_category_id=target_category_id,
        filters=[{"source": "metadata", "attribute_id": attr_id, "operator": "is_not_empty"}],
        attributes_by_id=attributes_by_id,
    )
    assert not item_matches_rule_filters(
        item=item,
        metadata_row=metadata_row,
        target_category_id=target_category_id,
        filters=[
            {
                "source": "metadata",
                "attribute_id": str(uuid4()),
                "operator": "equals",
                "value": "Saga",
            }
        ],
        attributes_by_id=attributes_by_id,
    )
