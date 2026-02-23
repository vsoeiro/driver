"""Shared upload-size/chunking policy constants."""

from __future__ import annotations

MAX_SIMPLE_UPLOAD_SIZE = 4 * 1024 * 1024  # 4MB
DEFAULT_CHUNK_SIZE = 327680 * 10  # ~3.2MB


def is_large_upload(size_bytes: int) -> bool:
    """Return True when upload should use resumable session flow."""
    return int(size_bytes or 0) > MAX_SIMPLE_UPLOAD_SIZE

