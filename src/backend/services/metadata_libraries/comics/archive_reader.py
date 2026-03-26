"""Shared comic archive extraction helpers for metadata and reader flows."""

from __future__ import annotations

import io
import logging
import os
import posixpath
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator
from xml.etree import ElementTree

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from backend.services.rar_tools import ensure_rar_backend

logger = logging.getLogger(__name__)

SUPPORTED_COMIC_EXTENSIONS = {
    "cbz",
    "zip",
    "cbw",
    "pdf",
    "epub",
    "cbr",
    "rar",
    "cb7",
    "7z",
    "cbt",
    "tar",
}
READER_COMIC_EXTENSIONS = {
    "cbz",
    "zip",
    "cbw",
    "cbr",
    "rar",
    "cb7",
    "7z",
    "cbt",
    "tar",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}
NON_COMIC_EXTRACTION_MARKERS = (
    "archive has no image pages",
    "no image pages",
    "extracted only empty cover files",
    "epub has no cover image",
    "epub missing",
    "epub container has no rootfile",
    "epub opf manifest not found",
    "cannot open the file as archive",
    "is not rar archive",
    "not a rar archive",
    "not a rar file",
)
RAR_BACKEND_FAILURE_MARKERS = (
    "pathname cannot be converted",
    "unsupported method",
)
RAR_UTF8_LOCALE = "C.UTF-8"


@dataclass(slots=True)
class ComicExtractionResult:
    """Extraction payload with cover bytes and basic page metadata."""

    format: str
    page_count: int | None
    cover_bytes: bytes | None = None
    cover_extension: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractedComicPage:
    """One extracted page ready for reader delivery."""

    index: int
    filename: str
    width: int | None = None
    height: int | None = None


def file_extension(filename: str | None) -> str:
    """Return filename extension in lowercase without leading dot."""
    if not filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _container_from_extension(ext: str) -> str | None:
    if ext in {"zip", "cbz", "cbw"}:
        return "zip"
    if ext in {"rar", "cbr"}:
        return "rar"
    if ext in {"7z", "cb7"}:
        return "7z"
    if ext in {"tar", "cbt"}:
        return "tar"
    if ext == "epub":
        return "epub"
    if ext == "pdf":
        return "pdf"
    return None


def _detect_archive_container(local_path: str) -> str | None:
    try:
        with open(local_path, "rb") as handle:
            head = handle.read(560)
    except OSError:
        return None

    if head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "zip"
    if head.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")):
        return "rar"
    if head.startswith(b"\x37\x7a\xbc\xaf\x27\x1c"):
        return "7z"
    if head.startswith(b"%PDF-"):
        return "pdf"
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "tar"
    return None


def _ordered_image_names_and_count(image_names: Iterable[str]) -> tuple[list[str], int]:
    ordered = [name for name in image_names if name]
    ordered.sort(key=lambda value: value.lower())
    if not ordered:
        raise ValueError("Archive has no image pages")
    return ordered, len(ordered)


def _pick_first_non_empty_payload(
    ordered_names: list[str], *, reader: Callable[[str], bytes], source_label: str
) -> tuple[str, bytes]:
    for candidate_name in ordered_names:
        payload = reader(candidate_name)
        if payload:
            return candidate_name, payload
    raise ValueError(f"{source_label} extracted only empty cover files")


def _rar_cli_locale_overrides() -> dict[str, str]:
    return {
        "LANG": RAR_UTF8_LOCALE,
        "LC_ALL": RAR_UTF8_LOCALE,
        "LC_CTYPE": RAR_UTF8_LOCALE,
    }


def _rar_cli_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(_rar_cli_locale_overrides())
    return env


@contextmanager
def _temporary_rar_cli_locale() -> Iterator[None]:
    originals = {key: os.environ.get(key) for key in _rar_cli_locale_overrides()}
    try:
        os.environ.update(_rar_cli_locale_overrides())
        yield
    finally:
        for key, value in originals.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def is_non_comic_extraction_error(error_text: str) -> bool:
    normalized = str(error_text or "").lower()
    if any(marker in normalized for marker in RAR_BACKEND_FAILURE_MARKERS):
        return False
    return any(marker in normalized for marker in NON_COMIC_EXTRACTION_MARKERS)


def _run_container_extractor(
    local_path: str, *, fmt: str, container: str
) -> ComicExtractionResult:
    if container == "zip":
        return _extract_from_zip(local_path, fmt=fmt)
    if container == "rar":
        return _extract_from_rar(local_path, fmt=fmt)
    if container == "7z":
        return _extract_from_7z(local_path, fmt=fmt)
    if container == "tar":
        return _extract_from_tar(local_path, fmt=fmt)
    if container == "pdf":
        return _extract_from_pdf(local_path)
    raise ValueError(f"Unsupported fallback container: {container}")


def _extract_archive_with_fallback(
    local_path: str,
    *,
    fmt: str,
    primary_container: str,
    primary_error: Exception,
) -> ComicExtractionResult:
    detected = _detect_archive_container(local_path)
    attempts: list[tuple[str, str]] = []
    candidate_containers: list[str] = []
    if (
        detected
        and detected != primary_container
        and detected in {"zip", "rar", "7z", "tar", "pdf"}
    ):
        candidate_containers.append(detected)

    for container in ("zip", "rar", "7z", "tar", "pdf"):
        if container == primary_container or container in candidate_containers:
            continue
        candidate_containers.append(container)

    for container in candidate_containers:
        try:
            extracted = _run_container_extractor(
                local_path, fmt=fmt, container=container
            )
            extracted.details["fallback_used"] = container
            if detected:
                extracted.details["detected_container"] = detected
            extracted.details["primary_container"] = primary_container
            return extracted
        except Exception as exc:  # noqa: BLE001
            attempts.append((container, str(exc)))

    try:
        extracted = _extract_from_rar_with_7z(local_path, fmt=fmt)
        extracted.details["fallback_used"] = "rar_cli"
        if detected:
            extracted.details["detected_container"] = detected
        extracted.details["primary_container"] = primary_container
        return extracted
    except Exception as exc:  # noqa: BLE001
        attempts.append(("rar_cli", str(exc)))

    attempts_preview = "; ".join(f"{name}: {reason}" for name, reason in attempts[:5])
    raise ValueError(
        f"Archive extraction failed for .{fmt}. primary={primary_container}: {primary_error}. "
        f"fallbacks={attempts_preview}"
    )


def extract_comic_asset(local_path: str, extension: str) -> ComicExtractionResult:
    """Extract cover/page metadata from a supported comic container."""
    ext = extension.lower()
    if ext in {"zip", "cbz", "cbw"}:
        try:
            return _extract_from_zip(local_path, fmt=ext)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ZIP extraction failed for %s (%s). Trying archive fallbacks.",
                local_path,
                exc,
            )
            return _extract_archive_with_fallback(
                local_path,
                fmt=ext,
                primary_container="zip",
                primary_error=exc,
            )
    if ext in {"rar", "cbr"}:
        return _extract_from_rar(local_path, fmt=ext)
    if ext in {"7z", "cb7"}:
        try:
            return _extract_from_7z(local_path, fmt=ext)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "7Z extraction failed for %s (%s). Trying archive fallbacks.",
                local_path,
                exc,
            )
            return _extract_archive_with_fallback(
                local_path,
                fmt=ext,
                primary_container="7z",
                primary_error=exc,
            )
    if ext in {"tar", "cbt"}:
        try:
            return _extract_from_tar(local_path, fmt=ext)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "TAR extraction failed for %s (%s). Trying archive fallbacks.",
                local_path,
                exc,
            )
            return _extract_archive_with_fallback(
                local_path,
                fmt=ext,
                primary_container="tar",
                primary_error=exc,
            )
    if ext == "epub":
        return _extract_from_epub(local_path)
    if ext == "pdf":
        return _extract_from_pdf(local_path)
    raise ValueError(f"Unsupported comic extension: {ext}")


def _extract_from_zip(local_path: str, *, fmt: str) -> ComicExtractionResult:
    with zipfile.ZipFile(local_path, "r") as archive:
        image_names = [
            name
            for name in archive.namelist()
            if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_EXTENSIONS
        ]
        ordered_names, page_count = _ordered_image_names_and_count(image_names)
        cover_name, cover_bytes = _pick_first_non_empty_payload(
            ordered_names, reader=archive.read, source_label="ZIP"
        )
        cover_extension = Path(cover_name).suffix.lower().lstrip(".") or "jpg"
        return ComicExtractionResult(
            format=fmt,
            page_count=page_count,
            cover_bytes=cover_bytes,
            cover_extension=cover_extension,
            details={"cover_member": cover_name},
        )


def _extract_from_tar(local_path: str, *, fmt: str) -> ComicExtractionResult:
    with tarfile.open(local_path, "r:*") as archive:
        image_members = [
            member
            for member in archive.getmembers()
            if member.isfile() and Path(member.name).suffix.lower() in IMAGE_EXTENSIONS
        ]
        member_by_name = {member.name: member for member in image_members}
        ordered_names, page_count = _ordered_image_names_and_count(member_by_name.keys())

        def _read_member(name: str) -> bytes:
            member = member_by_name[name]
            extracted = archive.extractfile(member)
            if extracted is None:
                return b""
            return extracted.read()

        cover_name, cover_bytes = _pick_first_non_empty_payload(
            ordered_names, reader=_read_member, source_label="TAR"
        )
        cover_extension = Path(cover_name).suffix.lower().lstrip(".") or "jpg"
        return ComicExtractionResult(
            format=fmt,
            page_count=page_count,
            cover_bytes=cover_bytes,
            cover_extension=cover_extension,
            details={"cover_member": cover_name},
        )


def _extract_from_rar(local_path: str, *, fmt: str) -> ComicExtractionResult:
    try:
        import rarfile  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError("RAR support requires optional dependency 'rarfile'") from exc
    if not ensure_rar_backend():
        raise ValueError(
            "RAR backend tool not available. Configure COMIC_RAR_TOOLS_DIR and optionally "
            "COMIC_RAR_TOOL_DOWNLOAD_URL / COMIC_RAR_TOOL_PATH."
        )

    try:
        with _temporary_rar_cli_locale():
            with rarfile.RarFile(local_path, "r") as archive:
                image_names = [
                    info.filename
                    for info in archive.infolist()
                    if not info.is_dir()
                    and Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS
                ]
                ordered_names, page_count = _ordered_image_names_and_count(image_names)
                cover_name, cover_bytes = _pick_first_non_empty_payload(
                    ordered_names, reader=archive.read, source_label="RAR"
                )
                cover_extension = Path(cover_name).suffix.lower().lstrip(".") or "jpg"
                return ComicExtractionResult(
                    format=fmt,
                    page_count=page_count,
                    cover_bytes=cover_bytes,
                    cover_extension=cover_extension,
                    details={"cover_member": cover_name},
                )
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc).lower()
        if any(marker in error_text for marker in RAR_BACKEND_FAILURE_MARKERS):
            logger.warning(
                "RAR Python backend failed for %s (%s). Trying 7z/7zr fallback.",
                local_path,
                exc,
            )
            return _extract_from_rar_with_7z(local_path, fmt=fmt)
        raise


def _find_7z_tools() -> list[tuple[str, str]]:
    from backend.core.config import get_settings

    settings = get_settings()
    candidates: list[tuple[str, str]] = []
    tools_dir_raw = getattr(settings, "comic_rar_tools_dir", None)
    explicit_tool = getattr(settings, "comic_rar_tool_path", None)
    if explicit_tool:
        explicit_path = Path(explicit_tool).expanduser()
        if explicit_path.exists():
            kind = "7zr" if explicit_path.name.lower().startswith("7zr") else "7z"
            candidates.append((str(explicit_path), kind))

    if tools_dir_raw:
        tools_dir = Path(tools_dir_raw).expanduser()
        for name in ("7zr", "7zr.exe", "7z", "7z.exe"):
            path = tools_dir / name
            if path.exists():
                kind = "7zr" if name.startswith("7zr") else "7z"
                candidates.append((str(path), kind))

    for name, kind in (("7zr", "7zr"), ("7zr.exe", "7zr"), ("7z", "7z"), ("7z.exe", "7z")):
        path = shutil.which(name)
        if path:
            candidates.append((path, kind))

    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tool, kind in candidates:
        if tool in seen:
            continue
        seen.add(tool)
        unique.append((tool, kind))
    return unique


def _build_7z_extract_command(
    tool: str,
    kind: str,
    *,
    extract_dir: str,
    local_path: str,
) -> list[str]:
    if kind == "7zr":
        return [tool, "x", "-y", f"-o{extract_dir}", local_path]
    return [tool, "x", "-y", "-spd", f"-o{extract_dir}", local_path]


def _extract_from_rar_with_7z(local_path: str, *, fmt: str) -> ComicExtractionResult:
    failures: list[str] = []
    tools = _find_7z_tools()
    if not tools:
        raise ValueError(
            "RAR backend failed and no 7z/7zr CLI fallback is available. "
            "Configure COMIC_RAR_TOOL_PATH or COMIC_RAR_TOOLS_DIR."
        )

    for tool, kind in tools:
        with tempfile.TemporaryDirectory(prefix="comic_rar_7z_") as extract_dir:
            extract_cmd = _build_7z_extract_command(
                tool,
                kind,
                extract_dir=extract_dir,
                local_path=local_path,
            )
            extract_proc = subprocess.run(
                extract_cmd,
                capture_output=True,
                check=False,
                env=_rar_cli_subprocess_env(),
            )
            stderr = extract_proc.stderr.decode("utf-8", errors="ignore").strip()

            root = Path(extract_dir)
            image_paths = [
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ]
            image_paths.sort(key=lambda path: path.relative_to(root).as_posix().lower())
            cover_path = next(
                (path for path in image_paths if path.stat().st_size > 0),
                None,
            )
            if cover_path is not None:
                cover_bytes = cover_path.read_bytes()
                cover_member = cover_path.relative_to(root).as_posix()
                cover_extension = cover_path.suffix.lower().lstrip(".") or "jpg"
                return ComicExtractionResult(
                    format=fmt,
                    page_count=len(image_paths),
                    cover_bytes=cover_bytes,
                    cover_extension=cover_extension,
                    details={
                        "cover_member": cover_member,
                        "backend": "rar_cli_fallback",
                        "cli_tool": tool,
                        "cli_kind": kind,
                        "cli_return_code": extract_proc.returncode,
                        "cli_stderr": stderr[:2000] if stderr else "",
                    },
                )

            if extract_proc.returncode not in (0, 1):
                failures.append(
                    f"{Path(tool).name}: code={extract_proc.returncode} stderr={stderr[:400]}"
                )
            elif image_paths:
                failures.append(
                    f"{Path(tool).name}: extracted only empty image files"
                )
            else:
                failures.append(
                    f"{Path(tool).name}: no image pages (stderr={stderr[:200]})"
                )

    raise ValueError(
        "RAR CLI extraction failed across available tools: "
        + " | ".join(failures[:4])
    )


def _resolve_extracted_candidate_path(base_dir: str, candidate_name: str) -> Path | None:
    safe_parts = _normalize_member_parts(candidate_name)
    if safe_parts:
        safe_path = Path(base_dir, *safe_parts)
        if safe_path.exists():
            return safe_path
    raw_path = Path(base_dir) / Path(candidate_name)
    if raw_path.exists():
        return raw_path
    return None


def _extract_from_7z(local_path: str, *, fmt: str) -> ComicExtractionResult:
    try:
        import py7zr  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError("7Z support requires optional dependency 'py7zr'") from exc

    with py7zr.SevenZipFile(local_path, "r") as archive:
        image_names = [
            name
            for name in archive.getnames()
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS
        ]
        ordered_names, page_count = _ordered_image_names_and_count(image_names)
        with tempfile.TemporaryDirectory(prefix="comic_7z_cover_") as temp_dir:
            cover_name = ""
            cover_bytes = b""
            for candidate in ordered_names:
                archive.extract(path=temp_dir, targets=[candidate])
                candidate_path = _resolve_extracted_candidate_path(temp_dir, candidate)
                if candidate_path is None or not candidate_path.exists():
                    continue
                candidate_bytes = candidate_path.read_bytes()
                if candidate_bytes:
                    cover_name = candidate
                    cover_bytes = candidate_bytes
                    break
            if not cover_name:
                raise ValueError("7Z extracted only empty cover files")
        cover_extension = Path(cover_name).suffix.lower().lstrip(".") or "jpg"
        return ComicExtractionResult(
            format=fmt,
            page_count=page_count,
            cover_bytes=cover_bytes,
            cover_extension=cover_extension,
            details={"cover_member": cover_name},
        )


def _extract_from_epub(local_path: str) -> ComicExtractionResult:
    with zipfile.ZipFile(local_path, "r") as archive:
        names = set(archive.namelist())
        if "META-INF/container.xml" not in names:
            raise ValueError("EPUB missing META-INF/container.xml")

        container_xml = archive.read("META-INF/container.xml")
        container_root = ElementTree.fromstring(container_xml)
        rootfile_el = container_root.find(".//{*}rootfile")
        if rootfile_el is None:
            raise ValueError("EPUB container has no rootfile")
        opf_path = rootfile_el.attrib.get("full-path")
        if not opf_path or opf_path not in names:
            raise ValueError("EPUB OPF manifest not found")

        opf_xml = archive.read(opf_path)
        opf_root = ElementTree.fromstring(opf_xml)
        ns = {
            "opf": opf_root.tag.partition("}")[0].strip("{"),
        }

        manifest_items = {
            item.attrib.get("id"): item
            for item in opf_root.findall(".//opf:item", ns)
            if item.attrib.get("id")
        }
        spine_items = [
            itemref.attrib.get("idref")
            for itemref in opf_root.findall(".//opf:spine/opf:itemref", ns)
            if itemref.attrib.get("idref")
        ]
        page_count = len(spine_items) if spine_items else None
        opf_dir = posixpath.dirname(opf_path)

        metadata_el = opf_root.find(".//opf:metadata", ns)
        cover_id = None
        if metadata_el is not None:
            for meta_el in metadata_el.findall(".//opf:meta", ns):
                if meta_el.attrib.get("name", "").lower() == "cover":
                    cover_id = meta_el.attrib.get("content")
                    break

        cover_bytes: bytes | None = None
        cover_extension: str | None = None
        resolved_cover_member: str | None = None
        if cover_id and cover_id in manifest_items:
            cover_href = manifest_items[cover_id].attrib.get("href")
            if cover_href:
                cover_member = posixpath.normpath(posixpath.join(opf_dir, cover_href))
                if cover_member in names:
                    resolved_cover_member = cover_member
                    cover_bytes = archive.read(cover_member)
                    cover_extension = (
                        Path(cover_member).suffix.lower().lstrip(".") or "jpg"
                    )

        if cover_bytes is None:
            image_names = [
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and Path(name).suffix.lower() in IMAGE_EXTENSIONS
            ]
            image_names.sort(key=lambda value: value.lower())
            if image_names:
                resolved_cover_member = image_names[0]
                cover_bytes = archive.read(resolved_cover_member)
                cover_extension = (
                    Path(resolved_cover_member).suffix.lower().lstrip(".") or "jpg"
                )

        if cover_bytes is None:
            raise ValueError("EPUB has no cover image")

        return ComicExtractionResult(
            format="epub",
            page_count=page_count,
            cover_bytes=cover_bytes,
            cover_extension=cover_extension,
            details={"cover_member": resolved_cover_member},
        )


def _extract_from_pdf(local_path: str) -> ComicExtractionResult:
    reader = PdfReader(local_path)
    cover_bytes: bytes | None = None
    cover_extension: str | None = None
    cover_page_index: int | None = None

    for page_index, page in enumerate(reader.pages):
        images = getattr(page, "images", None)
        if not images:
            continue
        for image in images:
            data = getattr(image, "data", None)
            if not data:
                continue
            cover_bytes = bytes(data)
            image_name = getattr(image, "name", "") or ""
            suffix = Path(image_name).suffix.lower().lstrip(".")
            cover_extension = suffix or "jpg"
            cover_page_index = page_index
            break
        if cover_bytes:
            break

    return ComicExtractionResult(
        format="pdf",
        page_count=len(reader.pages),
        cover_bytes=cover_bytes,
        cover_extension=cover_extension,
        details={
            "cover": "extracted_from_embedded_image"
            if cover_bytes
            else "embedded_image_not_found",
            "cover_page_index": cover_page_index,
        },
    )


def _normalize_member_parts(raw_name: str | None) -> list[str] | None:
    text = str(raw_name or "").replace("\\", "/").strip()
    if not text:
        return None

    parts: list[str] = []
    for raw_part in text.split("/"):
        part = str(raw_part or "").strip()
        if not part or part == ".":
            continue
        if part == "..":
            return None
        safe_part = Path(part).name.strip()
        if not safe_part or safe_part in {".", ".."}:
            return None
        parts.append(safe_part)
    return parts or None


def _image_dimensions(payload: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(payload)) as image:
            return int(image.width), int(image.height)
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None


def _write_reader_page(
    output_dir: str,
    *,
    index: int,
    source_name: str,
    payload: bytes,
) -> ExtractedComicPage | None:
    if not payload:
        return None

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    suffix = Path(source_name).suffix.lower() or ".jpg"
    target_name = f"page-{index + 1:04d}{suffix}"
    target_path = Path(output_dir) / target_name
    target_path.write_bytes(payload)
    width, height = _image_dimensions(payload)
    return ExtractedComicPage(
        index=index,
        filename=target_name,
        width=width,
        height=height,
    )


def _finalize_reader_pages(pages: list[ExtractedComicPage]) -> list[ExtractedComicPage]:
    if not pages:
        raise ValueError("Archive has no image pages")
    return [
        ExtractedComicPage(
            index=page_index,
            filename=page.filename,
            width=page.width,
            height=page.height,
        )
        for page_index, page in enumerate(pages)
    ]


def extract_comic_pages(
    local_path: str,
    extension: str,
    output_dir: str,
) -> list[ExtractedComicPage]:
    """Extract all ordered image pages from a reader-supported archive."""
    ext = extension.lower()
    if ext not in READER_COMIC_EXTENSIONS:
        raise ValueError(f"Comic reader does not support .{ext or 'unknown'}")

    container = _container_from_extension(ext)
    if container == "zip":
        try:
            return _extract_pages_from_zip(local_path, output_dir=output_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ZIP page extraction failed for %s (%s). Trying archive fallbacks.",
                local_path,
                exc,
            )
            return _extract_pages_with_fallback(
                local_path,
                output_dir=output_dir,
                primary_container="zip",
                primary_error=exc,
            )
    if container == "rar":
        return _extract_pages_from_rar(local_path, output_dir=output_dir)
    if container == "7z":
        try:
            return _extract_pages_from_7z(local_path, output_dir=output_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "7Z page extraction failed for %s (%s). Trying archive fallbacks.",
                local_path,
                exc,
            )
            return _extract_pages_with_fallback(
                local_path,
                output_dir=output_dir,
                primary_container="7z",
                primary_error=exc,
            )
    if container == "tar":
        try:
            return _extract_pages_from_tar(local_path, output_dir=output_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "TAR page extraction failed for %s (%s). Trying archive fallbacks.",
                local_path,
                exc,
            )
            return _extract_pages_with_fallback(
                local_path,
                output_dir=output_dir,
                primary_container="tar",
                primary_error=exc,
            )
    raise ValueError(f"Comic reader does not support .{ext}")


def _extract_pages_with_fallback(
    local_path: str,
    *,
    output_dir: str,
    primary_container: str,
    primary_error: Exception,
) -> list[ExtractedComicPage]:
    detected = _detect_archive_container(local_path)
    attempts: list[tuple[str, str]] = []
    candidate_containers: list[str] = []
    if (
        detected
        and detected != primary_container
        and detected in {"zip", "rar", "7z", "tar"}
    ):
        candidate_containers.append(detected)

    for container in ("zip", "rar", "7z", "tar"):
        if container == primary_container or container in candidate_containers:
            continue
        candidate_containers.append(container)

    for container in candidate_containers:
        try:
            return _extract_pages_by_container(
                local_path,
                output_dir=output_dir,
                container=container,
            )
        except Exception as exc:  # noqa: BLE001
            attempts.append((container, str(exc)))

    attempts_preview = "; ".join(f"{name}: {reason}" for name, reason in attempts[:5])
    raise ValueError(
        f"Page extraction failed. primary={primary_container}: {primary_error}. fallbacks={attempts_preview}"
    )


def _extract_pages_by_container(
    local_path: str,
    *,
    output_dir: str,
    container: str,
) -> list[ExtractedComicPage]:
    if container == "zip":
        return _extract_pages_from_zip(local_path, output_dir=output_dir)
    if container == "rar":
        return _extract_pages_from_rar(local_path, output_dir=output_dir)
    if container == "7z":
        return _extract_pages_from_7z(local_path, output_dir=output_dir)
    if container == "tar":
        return _extract_pages_from_tar(local_path, output_dir=output_dir)
    raise ValueError(f"Unsupported page extraction container: {container}")


def _extract_pages_from_zip(local_path: str, *, output_dir: str) -> list[ExtractedComicPage]:
    pages: list[ExtractedComicPage] = []
    with zipfile.ZipFile(local_path, "r") as archive:
        image_names = [
            name
            for name in archive.namelist()
            if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_EXTENSIONS
        ]
        ordered_names, _ = _ordered_image_names_and_count(image_names)
        for candidate in ordered_names:
            page = _write_reader_page(
                output_dir,
                index=len(pages),
                source_name=candidate,
                payload=archive.read(candidate),
            )
            if page is not None:
                pages.append(page)
    return _finalize_reader_pages(pages)


def _extract_pages_from_tar(local_path: str, *, output_dir: str) -> list[ExtractedComicPage]:
    pages: list[ExtractedComicPage] = []
    with tarfile.open(local_path, "r:*") as archive:
        image_members = [
            member
            for member in archive.getmembers()
            if member.isfile() and Path(member.name).suffix.lower() in IMAGE_EXTENSIONS
        ]
        member_by_name = {member.name: member for member in image_members}
        ordered_names, _ = _ordered_image_names_and_count(member_by_name.keys())
        for candidate in ordered_names:
            extracted = archive.extractfile(member_by_name[candidate])
            payload = extracted.read() if extracted is not None else b""
            page = _write_reader_page(
                output_dir,
                index=len(pages),
                source_name=candidate,
                payload=payload,
            )
            if page is not None:
                pages.append(page)
    return _finalize_reader_pages(pages)


def _extract_pages_from_rar(local_path: str, *, output_dir: str) -> list[ExtractedComicPage]:
    try:
        import rarfile  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError("RAR support requires optional dependency 'rarfile'") from exc
    if not ensure_rar_backend():
        raise ValueError(
            "RAR backend tool not available. Configure COMIC_RAR_TOOLS_DIR and optionally "
            "COMIC_RAR_TOOL_DOWNLOAD_URL / COMIC_RAR_TOOL_PATH."
        )

    pages: list[ExtractedComicPage] = []
    try:
        with _temporary_rar_cli_locale():
            with rarfile.RarFile(local_path, "r") as archive:
                image_names = [
                    info.filename
                    for info in archive.infolist()
                    if not info.is_dir()
                    and Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS
                ]
                ordered_names, _ = _ordered_image_names_and_count(image_names)
                for candidate in ordered_names:
                    page = _write_reader_page(
                        output_dir,
                        index=len(pages),
                        source_name=candidate,
                        payload=archive.read(candidate),
                    )
                    if page is not None:
                        pages.append(page)
        return _finalize_reader_pages(pages)
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc).lower()
        if any(marker in error_text for marker in RAR_BACKEND_FAILURE_MARKERS):
            logger.warning(
                "RAR page extraction failed for %s (%s). Trying 7z/7zr fallback.",
                local_path,
                exc,
            )
            return _extract_pages_from_rar_with_7z(local_path, output_dir=output_dir)
        raise


def _extract_pages_from_rar_with_7z(
    local_path: str,
    *,
    output_dir: str,
) -> list[ExtractedComicPage]:
    tools = _find_7z_tools()
    failures: list[str] = []
    if not tools:
        raise ValueError(
            "RAR backend failed and no 7z/7zr CLI fallback is available. "
            "Configure COMIC_RAR_TOOL_PATH or COMIC_RAR_TOOLS_DIR."
        )

    for tool, kind in tools:
        with tempfile.TemporaryDirectory(prefix="comic_reader_rar_") as extract_dir:
            extract_cmd = _build_7z_extract_command(
                tool,
                kind,
                extract_dir=extract_dir,
                local_path=local_path,
            )
            extract_proc = subprocess.run(
                extract_cmd,
                capture_output=True,
                check=False,
                env=_rar_cli_subprocess_env(),
            )
            stderr = extract_proc.stderr.decode("utf-8", errors="ignore").strip()
            root = Path(extract_dir)
            image_paths = [
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ]
            image_paths.sort(key=lambda path: path.relative_to(root).as_posix().lower())
            if image_paths:
                pages: list[ExtractedComicPage] = []
                for image_path in image_paths:
                    page = _write_reader_page(
                        output_dir,
                        index=len(pages),
                        source_name=image_path.name,
                        payload=image_path.read_bytes(),
                    )
                    if page is not None:
                        pages.append(page)
                return _finalize_reader_pages(pages)

            if extract_proc.returncode not in (0, 1):
                failures.append(
                    f"{Path(tool).name}: code={extract_proc.returncode} stderr={stderr[:400]}"
                )
            else:
                failures.append(
                    f"{Path(tool).name}: no image pages (stderr={stderr[:200]})"
                )

    raise ValueError(
        "RAR CLI page extraction failed across available tools: "
        + " | ".join(failures[:4])
    )


def _extract_pages_from_7z(local_path: str, *, output_dir: str) -> list[ExtractedComicPage]:
    try:
        import py7zr  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError("7Z support requires optional dependency 'py7zr'") from exc

    with py7zr.SevenZipFile(local_path, "r") as archive:
        image_names = [
            name
            for name in archive.getnames()
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS
        ]
        ordered_names, _ = _ordered_image_names_and_count(image_names)
        with tempfile.TemporaryDirectory(prefix="comic_reader_7z_") as temp_dir:
            archive.extract(path=temp_dir, targets=ordered_names)
            pages: list[ExtractedComicPage] = []
            for candidate in ordered_names:
                candidate_path = _resolve_extracted_candidate_path(temp_dir, candidate)
                if candidate_path is None or not candidate_path.exists():
                    continue
                page = _write_reader_page(
                    output_dir,
                    index=len(pages),
                    source_name=candidate,
                    payload=candidate_path.read_bytes(),
                )
                if page is not None:
                    pages.append(page)
        return _finalize_reader_pages(pages)
