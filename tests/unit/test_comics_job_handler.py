from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from backend.workers.handlers.comics import extract_comic_assets_handler


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_extract_comic_assets_handler_processes_indexed_item_groups():
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _RowsResult([("item-1", "Alpha", "cbz", "file", 101)]),
                _RowsResult([("item-2", "Beta", "cbr", "file", 202)]),
            ]
        ),
        commit=AsyncMock(),
    )
    progress = SimpleNamespace(
        job_id=UUID("11111111-1111-1111-1111-111111111111"),
        flush_every_items=0,
        current=0,
        set_total=AsyncMock(),
        update_metrics=AsyncMock(),
        flush=AsyncMock(),
    )
    service = SimpleNamespace(
        process_indexed_items=AsyncMock(
            side_effect=[
                {
                    "total": 1,
                    "mapped": 1,
                    "skipped": 0,
                    "failed": 0,
                    "error_items": [],
                    "error_items_truncated": 0,
                },
                {
                    "total": 1,
                    "mapped": 0,
                    "skipped": 1,
                    "failed": 0,
                    "error_items": [
                        {"item_id": "item-2", "reason": "Skipped non-comic content"}
                    ],
                    "error_items_truncated": 0,
                },
            ]
        )
    )

    with (
        patch(
            "backend.workers.handlers.comics.JobProgressReporter.from_payload",
            return_value=progress,
        ),
        patch(
            "backend.workers.handlers.comics.ComicMetadataService",
            return_value=service,
        ),
    ):
        result = await extract_comic_assets_handler(
            {
                "indexed_item_groups": [
                    {
                        "account_id": "00000000-0000-0000-0000-000000000001",
                        "item_ids": ["item-1"],
                    },
                    {
                        "account_id": "00000000-0000-0000-0000-000000000002",
                        "item_ids": ["item-2"],
                    },
                ],
                "use_indexed_items": True,
            },
            session,
        )

    assert result["total"] == 2
    assert result["mapped"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert len(result["error_items"]) == 1
    assert service.process_indexed_items.await_count == 2
    session.commit.assert_awaited_once()
    assert progress.set_total.await_count == 2
