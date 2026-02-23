"""Metadata rules routes."""

from __future__ import annotations

from backend.api.routes.metadata_route_utils import build_metadata_router


router = build_metadata_router(lambda path: path.startswith("/metadata/rules"))
