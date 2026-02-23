"""Metadata route composition module."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.routes import (
    metadata_categories,
    metadata_items,
    metadata_libraries,
    metadata_layouts,
    metadata_rules,
    metadata_series,
)
from backend.api.routes.metadata_impl import (
    _can_inline_edit_attribute,
    _coerce_attribute_value,
    delete_category,
)

router = APIRouter()
router.include_router(metadata_categories.router)
router.include_router(metadata_layouts.router)
router.include_router(metadata_series.router)
router.include_router(metadata_items.router)
router.include_router(metadata_rules.router)
router.include_router(metadata_libraries.router)

__all__ = [
    "router",
    "_coerce_attribute_value",
    "_can_inline_edit_attribute",
    "delete_category",
]
