from __future__ import annotations

import re
from typing import Any


_TOKEN_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_-]{8,})"),
    re.compile(r"(Bearer\s+[A-Za-z0-9._-]{8,})", re.IGNORECASE),
    re.compile(r"\b(?:MS|GOOGLE|DROPBOX|AI)_[A-Z_]*SECRET\b\s*[=:]\s*[^\s,;]+", re.IGNORECASE),
]
_EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def _mask_email(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}***{match.group(2)}"

    return _EMAIL_PATTERN.sub(_replace, text)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _TOKEN_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    redacted = _mask_email(redacted)
    return redacted


def redact_object(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): redact_object(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [redact_object(item) for item in value]
    if isinstance(value, tuple):
        return [redact_object(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
