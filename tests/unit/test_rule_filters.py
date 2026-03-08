from uuid import UUID

from backend.application.metadata.rule_filters import normalize_rule_filters
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
