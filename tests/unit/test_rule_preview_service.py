from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.application.metadata.repositories import ItemMetadataRepository
from backend.application.metadata.rule_preview_service import RulePreviewService
from backend.schemas.metadata import MetadataRulePreviewRequest


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


@pytest.mark.asyncio
async def test_rule_preview_counts_compliant_and_changed_items(monkeypatch):
    account_id = uuid4()
    target_category_id = uuid4()
    attr_id = uuid4()
    items = [
        SimpleNamespace(account_id=account_id, item_id="file-1", item_type="file", path="/Library/Saga/001.cbz"),
        SimpleNamespace(account_id=account_id, item_id="file-2", item_type="file", path="/Library/Saga/002.cbz"),
    ]
    metadata_by_pair = {
        (account_id, "file-1"): SimpleNamespace(category_id=target_category_id, values={str(attr_id): "Saga"}),
        (account_id, "file-2"): SimpleNamespace(category_id=target_category_id, values={str(attr_id): "Other"}),
    }
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _RowsResult(items),
                _RowsResult([SimpleNamespace(id=attr_id, data_type="text")]),
            ]
        )
    )

    async def _get_by_pairs(self, *, pairs):
        assert pairs == [(account_id, "file-1"), (account_id, "file-2")]
        return metadata_by_pair

    monkeypatch.setattr(ItemMetadataRepository, "get_by_account_item_pairs", _get_by_pairs)

    service = RulePreviewService(session)
    result = await service.preview(
        MetadataRulePreviewRequest(
            account_id=account_id,
            path_prefix="/Library",
            path_contains="Saga",
            include_folders=False,
            target_category_id=target_category_id,
            target_values={str(attr_id): "Saga"},
            apply_metadata=True,
            metadata_filters=[{"source": "path", "operator": "contains", "value": "Saga"}],
            limit=1,
        )
    )

    assert result.total_matches == 2
    assert result.to_change == 1
    assert result.already_compliant == 1
    assert result.sample_item_ids == ["file-2"]


@pytest.mark.asyncio
async def test_rule_preview_treats_remove_and_organize_actions_as_changes(monkeypatch):
    account_id = uuid4()
    target_category_id = uuid4()
    items = [
        SimpleNamespace(account_id=account_id, item_id="file-1", item_type="file", path="/Root/A.txt"),
        SimpleNamespace(account_id=account_id, item_id="file-2", item_type="file", path="/Root/B.txt"),
    ]
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _RowsResult(items),
                _RowsResult([]),
            ]
        )
    )

    async def _get_by_pairs(self, *, pairs):
        assert pairs == [(account_id, "file-1"), (account_id, "file-2")]
        return {
            (account_id, "file-2"): SimpleNamespace(category_id=target_category_id, values={"name": "Saga"}),
        }

    monkeypatch.setattr(ItemMetadataRepository, "get_by_account_item_pairs", _get_by_pairs)

    service = RulePreviewService(session)
    result = await service.preview(
        MetadataRulePreviewRequest(
            target_category_id=target_category_id,
            apply_metadata=False,
            apply_remove_metadata=True,
            apply_rename=True,
            target_values={},
            limit=1,
        )
    )

    assert result.total_matches == 2
    assert result.to_change == 2
    assert result.already_compliant == 0
    assert result.sample_item_ids == ["file-1"]
