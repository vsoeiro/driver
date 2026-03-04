from backend.api.routes.jobs import (
    _is_book_item_already_mapped,
    _is_comic_item_already_mapped,
    _is_image_item_already_analyzed,
)


def test_is_comic_item_already_mapped_true_when_cover_present():
    attr_ids = {
        "cover_item_id": "a1",
        "cover_account_id": "a2",
        "page_count": "a3",
        "file_format": "a4",
    }
    values = {"a1": "cover-123"}
    assert _is_comic_item_already_mapped(values, attr_ids) is True


def test_is_comic_item_already_mapped_false_when_fields_empty():
    attr_ids = {
        "cover_item_id": "a1",
        "cover_account_id": "a2",
        "page_count": "a3",
        "file_format": "a4",
    }
    values = {"a1": "", "a2": None}
    assert _is_comic_item_already_mapped(values, attr_ids) is False


def test_is_book_item_already_mapped_true_when_cover_present():
    attr_ids = {
        "cover_item_id": "a1",
        "cover_account_id": "a2",
        "page_count": "a3",
        "file_format": "a4",
    }
    values = {"a1": "cover-123"}
    assert _is_book_item_already_mapped(values, attr_ids) is True


def test_is_book_item_already_mapped_false_when_fields_empty():
    attr_ids = {
        "cover_item_id": "a1",
        "cover_account_id": "a2",
        "page_count": "a3",
        "file_format": "a4",
    }
    values = {"a1": "", "a2": None}
    assert _is_book_item_already_mapped(values, attr_ids) is False


def test_is_image_item_already_analyzed():
    assert _is_image_item_already_analyzed("completed") is True
    assert _is_image_item_already_analyzed("skipped") is False
    assert _is_image_item_already_analyzed(None) is False
