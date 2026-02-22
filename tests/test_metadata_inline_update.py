from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.routes.metadata import _can_inline_edit_attribute, _coerce_attribute_value


def _attr(data_type: str, name: str = "Field", options=None):
    return SimpleNamespace(data_type=data_type, name=name, options=options, is_locked=False, managed_by_plugin=False)


def test_coerce_attribute_number_success():
    attr = _attr("number", "Pages")
    assert _coerce_attribute_value(attr, "12") == 12
    assert _coerce_attribute_value(attr, "12.5") == 12.5


def test_coerce_attribute_number_invalid():
    attr = _attr("number", "Pages")
    with pytest.raises(HTTPException):
        _coerce_attribute_value(attr, "abc")


def test_coerce_attribute_boolean_success():
    attr = _attr("boolean", "Read")
    assert _coerce_attribute_value(attr, "true") is True
    assert _coerce_attribute_value(attr, "0") is False


def test_coerce_attribute_date_invalid():
    attr = _attr("date", "Published")
    with pytest.raises(HTTPException):
        _coerce_attribute_value(attr, "31/12/2025")


def test_coerce_attribute_select_invalid_option():
    attr = _attr("select", "Status", options={"options": ["New", "Done"]})
    with pytest.raises(HTTPException):
        _coerce_attribute_value(attr, "Other")


def test_coerce_attribute_blank_returns_none():
    attr = _attr("text", "Title")
    assert _coerce_attribute_value(attr, "   ") is None


def test_can_inline_edit_allows_non_readonly_comic_field():
    attr = _attr("text", "Series")
    attr.plugin_key = "comics_core"
    attr.plugin_field_key = "series"
    attr.is_locked = True
    attr.managed_by_plugin = True
    assert _can_inline_edit_attribute(attr) is True


def test_can_inline_edit_blocks_readonly_comic_field():
    attr = _attr("text", "Cover Item ID")
    attr.plugin_key = "comics_core"
    attr.plugin_field_key = "cover_item_id"
    attr.is_locked = True
    attr.managed_by_plugin = True
    assert _can_inline_edit_attribute(attr) is False
