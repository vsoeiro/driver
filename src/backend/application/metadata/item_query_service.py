"""Compatibility wrapper for item-list query use case."""

from __future__ import annotations

from backend.application.metadata.query_service import MetadataQueryService


class ItemQueryService(MetadataQueryService):
    """Specialized alias to keep item-query imports explicit."""

