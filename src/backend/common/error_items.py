"""Utilities for collecting bounded error-item payloads in job stats."""

from __future__ import annotations

from typing import Any


def ensure_error_fields(
    stats: dict[str, Any],
    *,
    items_key: str = "error_items",
    truncated_key: str = "error_items_truncated",
) -> None:
    """Ensure stats dict has list + counter slots for error item reporting."""
    if not isinstance(stats.get(items_key), list):
        stats[items_key] = []
    if truncated_key not in stats:
        stats[truncated_key] = 0


class ErrorItemsCollector:
    """Helper to add/merge error entries while enforcing max list size."""

    def __init__(
        self,
        stats: dict[str, Any],
        *,
        limit: int = 50,
        items_key: str = "error_items",
        truncated_key: str = "error_items_truncated",
    ) -> None:
        self.stats = stats
        self.limit = max(1, int(limit))
        self.items_key = items_key
        self.truncated_key = truncated_key
        ensure_error_fields(
            self.stats,
            items_key=self.items_key,
            truncated_key=self.truncated_key,
        )

    @property
    def _items(self) -> list[dict[str, str]]:
        items = self.stats.get(self.items_key)
        if isinstance(items, list):
            return items
        repaired: list[dict[str, str]] = []
        self.stats[self.items_key] = repaired
        return repaired

    def record(
        self,
        *,
        reason: str,
        item_id: str | None = None,
        item_name: str | None = None,
        account_id: str | None = None,
        stage: str | None = None,
    ) -> None:
        """Append one error entry or increment truncated counter."""
        items = self._items
        if len(items) >= self.limit:
            self.stats[self.truncated_key] = int(self.stats.get(self.truncated_key, 0) or 0) + 1
            return

        reason_text = str(reason or "Unknown error").strip() or "Unknown error"
        entry: dict[str, str] = {"reason": reason_text[:2000]}
        if item_id:
            entry["item_id"] = str(item_id)
        if item_name:
            entry["item_name"] = str(item_name)
        if account_id:
            entry["account_id"] = str(account_id)
        if stage:
            entry["stage"] = str(stage)
        items.append(entry)

    def merge(self, source: dict[str, Any]) -> None:
        """Merge another stats payload preserving this collector's limits."""
        source_items = source.get(self.items_key)
        if isinstance(source_items, list):
            for raw in source_items:
                if not isinstance(raw, dict):
                    continue
                self.record(
                    reason=str(raw.get("reason") or "Unknown error"),
                    item_id=str(raw.get("item_id")) if raw.get("item_id") else None,
                    item_name=str(raw.get("item_name")) if raw.get("item_name") else None,
                    account_id=str(raw.get("account_id")) if raw.get("account_id") else None,
                    stage=str(raw.get("stage")) if raw.get("stage") else None,
                )
        self.stats[self.truncated_key] = int(self.stats.get(self.truncated_key, 0) or 0) + int(
            source.get(self.truncated_key, 0) or 0
        )

