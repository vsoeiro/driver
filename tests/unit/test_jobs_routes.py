from backend.api.routes.jobs import _is_comic_item_already_mapped


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
