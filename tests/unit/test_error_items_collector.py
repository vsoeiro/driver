from backend.common.error_items import ErrorItemsCollector, ensure_error_fields


def test_error_items_collector_truncates_after_limit():
    stats: dict = {}
    collector = ErrorItemsCollector(stats, limit=2)

    collector.record(reason="err-1", item_id="1")
    collector.record(reason="err-2", item_id="2")
    collector.record(reason="err-3", item_id="3")

    assert len(stats["error_items"]) == 2
    assert stats["error_items_truncated"] == 1
    assert stats["error_items"][0]["item_id"] == "1"
    assert stats["error_items"][1]["item_id"] == "2"


def test_error_items_collector_merge_respects_limit_and_accumulates_truncated():
    target = {"error_items": [{"reason": "existing"}], "error_items_truncated": 0}
    source = {
        "error_items": [
            {"reason": "new-1", "item_id": "a"},
            {"reason": "new-2", "item_id": "b"},
        ],
        "error_items_truncated": 2,
    }

    collector = ErrorItemsCollector(target, limit=2)
    collector.merge(source)

    assert len(target["error_items"]) == 2
    assert target["error_items"][1]["item_id"] == "a"
    # One source item was dropped by limit + source already reported two truncated.
    assert target["error_items_truncated"] == 3


def test_ensure_error_fields_recovers_invalid_payload_shape():
    stats = {"error_items": "invalid"}
    ensure_error_fields(stats)
    assert stats["error_items"] == []
    assert stats["error_items_truncated"] == 0
