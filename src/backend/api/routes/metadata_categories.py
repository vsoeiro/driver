"""Category and attribute metadata routes."""

from __future__ import annotations

from backend.api.routes.metadata_route_utils import build_metadata_router


def _include_category_or_attribute(path: str) -> bool:
    if path.startswith("/metadata/attributes"):
        return True
    if path.startswith("/metadata/categories"):
        return not path.endswith("/series-summary")
    return False


router = build_metadata_router(_include_category_or_attribute)
