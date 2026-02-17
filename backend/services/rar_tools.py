"""RAR backend tool detection/bootstrap helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_RAR_TOOL_CHECKED = False
_RAR_TOOL_READY = False


def _candidate_tools(tools_dir: Path) -> list[Path]:
    names = [
        "unrar.exe",
        "unrar",
        "rar.exe",
        "rar",
        "7z.exe",
        "7z",
        "7za.exe",
        "7za",
        "tar.exe",
        "tar",
    ]
    return [tools_dir / name for name in names]


def _configure_rarfile_tool_paths(rarfile_module, tool_path: Path) -> None:
    tool = str(tool_path)
    rarfile_module.UNRAR_TOOL = tool
    rarfile_module.UNAR_TOOL = tool
    rarfile_module.BSDTAR_TOOL = tool
    rarfile_module.SEVENZIP_TOOL = tool
    if hasattr(rarfile_module, "SEVENZIP2_TOOL"):
        rarfile_module.SEVENZIP2_TOOL = tool


def _try_tool_setup(rarfile_module, tool_path: Path | None = None) -> bool:
    if tool_path is not None:
        _configure_rarfile_tool_paths(rarfile_module, tool_path)
    try:
        rarfile_module.tool_setup(force=True)
        return True
    except Exception:
        return False


def _download_tool(download_url: str, tools_dir: Path) -> Path | None:
    parsed = urlparse(download_url)
    file_name = Path(parsed.path).name or "rar_tool.bin"
    target = tools_dir / file_name
    try:
        response = httpx.get(download_url, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
        target.write_bytes(response.content)
        if os.name != "nt":
            target.chmod(0o755)
        return target
    except Exception as exc:
        logger.warning("Failed to download RAR tool from %s: %s", download_url, exc)
        return None


def ensure_rar_backend() -> bool:
    """Ensure rarfile has a working extraction backend.

    Returns True if ready, False otherwise.
    """
    global _RAR_TOOL_CHECKED, _RAR_TOOL_READY
    if _RAR_TOOL_CHECKED:
        return _RAR_TOOL_READY

    _RAR_TOOL_CHECKED = True
    try:
        import rarfile  # type: ignore[import-not-found]
    except Exception:
        _RAR_TOOL_READY = False
        return False

    settings = get_settings()
    tools_dir = Path(settings.comic_rar_tools_dir).expanduser()
    tools_dir.mkdir(parents=True, exist_ok=True)

    # 1) explicit path
    if settings.comic_rar_tool_path:
        explicit = Path(settings.comic_rar_tool_path).expanduser()
        if explicit.exists() and _try_tool_setup(rarfile, explicit):
            _RAR_TOOL_READY = True
            return True

    # 2) try system defaults
    if _try_tool_setup(rarfile):
        _RAR_TOOL_READY = True
        return True

    # 3) try tools dir known names
    for candidate in _candidate_tools(tools_dir):
        if candidate.exists() and _try_tool_setup(rarfile, candidate):
            _RAR_TOOL_READY = True
            return True

    # 4) optional auto-install
    if settings.comic_rar_tool_auto_install and settings.comic_rar_tool_download_url:
        downloaded = _download_tool(settings.comic_rar_tool_download_url, tools_dir)
        if downloaded and _try_tool_setup(rarfile, downloaded):
            _RAR_TOOL_READY = True
            return True

    _RAR_TOOL_READY = False
    return False
