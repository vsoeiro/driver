"""Compatibility wrapper for series-summary query use case."""

from __future__ import annotations

from backend.application.metadata.query_service import MetadataQueryService


class SeriesQueryService(MetadataQueryService):
    """Specialized alias to keep series-query imports explicit."""

