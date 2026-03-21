"""Shared upload-size/chunking policy constants."""

from __future__ import annotations

MAX_SIMPLE_UPLOAD_SIZE = 4 * 1024 * 1024  # 4MB
# Keep resumable chunks aligned to 256 KiB blocks so Google Drive can fully accept them.
DEFAULT_CHUNK_SIZE = 256 * 1024 * 12  # 3 MiB
MAX_RESUMABLE_UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024  # 16MB guard rail for /upload/chunk


def is_large_upload(size_bytes: int) -> bool:
    """Return True when upload should use resumable session flow."""
    return int(size_bytes or 0) > MAX_SIMPLE_UPLOAD_SIZE
