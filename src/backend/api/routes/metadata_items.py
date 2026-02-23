"""Item metadata routes."""

from __future__ import annotations

from backend.api.routes.metadata_route_utils import build_metadata_router


def _include_item_routes(path: str) -> bool:
    return path.startswith("/metadata/items") or path.startswith("/metadata/batches/")


router = build_metadata_router(_include_item_routes)
