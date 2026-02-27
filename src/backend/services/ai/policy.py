from __future__ import annotations

from dataclasses import dataclass

from backend.core.exceptions import DriveOrganizerError


@dataclass(slots=True)
class PolicyLimits:
    max_tool_calls: int
    max_rows_scanned: int


class PolicyEngine:
    def __init__(self, *, max_tool_calls: int, max_rows_scanned: int = 5000) -> None:
        self._limits = PolicyLimits(max_tool_calls=max(1, max_tool_calls), max_rows_scanned=max(100, max_rows_scanned))

    @property
    def limits(self) -> PolicyLimits:
        return self._limits

    def enforce_tool_budget(self, tool_calls_count: int) -> None:
        if tool_calls_count > self._limits.max_tool_calls:
            raise DriveOrganizerError(
                f"Tool-call budget exceeded ({tool_calls_count} > {self._limits.max_tool_calls})",
                status_code=400,
            )

    def require_confirmation_for_permission(self, permission: str) -> bool:
        return permission.lower().strip() != "read"
