"""RAR backend tool detection/bootstrap helpers."""

from __future__ import annotations

import ipaddress
import logging
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_RAR_TOOL_CHECKED = False
_RAR_TOOL_READY = False
_SUSPICIOUS_TOOL_NAMES = {
    "unrarw64.exe",
    "unrarw32.exe",
    "unrardll.exe",
}
MAX_TOOL_DOWNLOAD_BYTES = 64 * 1024 * 1024


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


def _is_cli_safe_tool(tool_path: Path) -> bool:
    name = tool_path.name.lower()
    if name in _SUSPICIOUS_TOOL_NAMES:
        return False
    if "winrar" in name:
        return False
    return True


def _try_tool_setup(rarfile_module, tool_path: Path | None = None) -> bool:
    if tool_path is not None:
        if not _is_cli_safe_tool(tool_path):
            logger.warning("Ignoring non-headless RAR tool candidate: %s", tool_path)
            return False
        _configure_rarfile_tool_paths(rarfile_module, tool_path)
    try:
        rarfile_module.tool_setup(force=True)
        return True
    except Exception:
        return False


def _download_tool(download_url: str, tools_dir: Path) -> Path | None:
    if not _is_safe_download_url(download_url):
        logger.warning("Rejected insecure RAR tool download URL: %s", download_url)
        return None

    parsed = urlparse(download_url)
    file_name = Path(parsed.path).name or "rar_tool.bin"
    target = tools_dir / file_name
    try:
        downloaded = 0
        with httpx.stream("GET", download_url, timeout=60.0, follow_redirects=True) as response:
            response.raise_for_status()
            final_url = str(response.url)
            if not _is_safe_download_url(final_url):
                logger.warning("Rejected redirected RAR tool URL: %s", final_url)
                return None
            with target.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > MAX_TOOL_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"RAR tool download exceeds {MAX_TOOL_DOWNLOAD_BYTES // (1024 * 1024)}MB limit"
                        )
                    handle.write(chunk)

        if os.name != "nt":
            target.chmod(0o755)
        if not _is_cli_safe_tool(target):
            logger.warning("Downloaded tool looks interactive and will be ignored: %s", target)
            return None
        return target
    except Exception as exc:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        logger.warning("Failed to download RAR tool from %s: %s", download_url, exc)
        return None


def _is_safe_download_url(download_url: str) -> bool:
    parsed = urlparse(download_url)
    if parsed.scheme.lower() != "https":
        return False
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    except ValueError:
        # Not an IP literal; keep host-based URL.
        pass
    return True


def _find_system_candidates() -> list[Path]:
    names = ["unrar", "rar", "7z", "7za", "tar", "bsdtar"]
    found: list[Path] = []
    for name in names:
        path = shutil.which(name)
        if path:
            found.append(Path(path))
    windows_defaults = [
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ]
    for candidate in windows_defaults:
        if candidate.exists():
            found.append(candidate)
    return found


def _try_install_7zip_windows() -> bool:
    if os.name != "nt":
        return False
    if not shutil.which("winget"):
        return False
    try:
        proc = subprocess.run(
            [
                "winget",
                "install",
                "--id",
                "7zip.7zip",
                "--exact",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--silent",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0
    except Exception:
        return False


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

    # 2) try rarfile default system lookup
    if _try_tool_setup(rarfile):
        logger.info("RAR backend ready using system defaults")
        _RAR_TOOL_READY = True
        return True

    # 3) try PATH-discovered binaries explicitly
    for candidate in _find_system_candidates():
        if _try_tool_setup(rarfile, candidate):
            logger.info("RAR backend ready using system tool: %s", candidate)
            _RAR_TOOL_READY = True
            return True

    # 4) try tools dir known names
    for candidate in _candidate_tools(tools_dir):
        if candidate.exists() and _try_tool_setup(rarfile, candidate):
            logger.info("RAR backend ready using local tool: %s", candidate)
            _RAR_TOOL_READY = True
            return True

    # 5) optional auto-install
    if settings.comic_rar_tool_auto_install:
        # Windows first: prefer installing a headless 7z binary from winget.
        if _try_install_7zip_windows():
            for candidate in _find_system_candidates():
                if _try_tool_setup(rarfile, candidate):
                    logger.info("RAR backend ready after 7-Zip install: %s", candidate)
                    _RAR_TOOL_READY = True
                    return True

        download_url = settings.comic_rar_tool_download_url or "https://www.7-zip.org/a/7zr.exe"
        downloaded = _download_tool(download_url, tools_dir)
        if downloaded and _try_tool_setup(rarfile, downloaded):
            logger.info("RAR backend ready using downloaded tool: %s", downloaded)
            _RAR_TOOL_READY = True
            return True

    _RAR_TOOL_READY = False
    return False
