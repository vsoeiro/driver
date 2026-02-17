"""Comic extraction and metadata mapping helpers."""

from __future__ import annotations

import io
import posixpath
import tarfile
import tempfile
import zipfile
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID
from xml.etree import ElementTree

from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.db.models import ItemMetadata, LinkedAccount
from backend.services.metadata_plugins import MetadataPluginService
from backend.services.plugin_settings import ComicRuntimeSettings, PluginSettingsService
from backend.services.rar_tools import ensure_rar_backend
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager

logger = logging.getLogger(__name__)
COMIC_MAPPING_COMMIT_BATCH_SIZE = 10

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
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}


@dataclass(slots=True)
class ComicExtractionResult:
    format: str
    page_count: int | None
    cover_bytes: bytes | None = None
    cover_extension: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def file_extension(filename: str | None) -> str:
    if not filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def extract_comic_asset(local_path: str, extension: str) -> ComicExtractionResult:
    ext = extension.lower()
    if ext in {"zip", "cbz", "cbw"}:
        return _extract_from_zip(local_path, fmt=ext)
    if ext in {"rar", "cbr"}:
        return _extract_from_rar(local_path, fmt=ext)
    if ext in {"7z", "cb7"}:
        return _extract_from_7z(local_path, fmt=ext)
    if ext in {"tar", "cbt"}:
        return _extract_from_tar(local_path, fmt=ext)
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
        cover_name, page_count = _select_cover_and_count(image_names)
        cover_bytes = archive.read(cover_name)
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
        image_names = [member.name for member in image_members]
        cover_name, page_count = _select_cover_and_count(image_names)
        cover_member = next(member for member in image_members if member.name == cover_name)
        extracted = archive.extractfile(cover_member)
        if extracted is None:
            raise ValueError("Failed to extract TAR cover image")
        cover_bytes = extracted.read()
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
        with rarfile.RarFile(local_path, "r") as archive:
            image_names = [
                info.filename
                for info in archive.infolist()
                if not info.is_dir() and Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS
            ]
            cover_name, page_count = _select_cover_and_count(image_names)
            cover_bytes = archive.read(cover_name)
            if not cover_bytes:
                raise ValueError("RAR backend returned empty bytes")
            cover_extension = Path(cover_name).suffix.lower().lstrip(".") or "jpg"
            return ComicExtractionResult(
                format=fmt,
                page_count=page_count,
                cover_bytes=cover_bytes,
                cover_extension=cover_extension,
                details={"cover_member": cover_name, "backend": "rarfile"},
            )
    except Exception as exc:
        logger.warning("rarfile extraction failed for %s: %s. Falling back to 7z CLI.", local_path, exc)
        return _extract_from_rar_with_7z(local_path, fmt=fmt)


def _find_7z_tool() -> str | None:
    candidates = ["7z", "7za", "7zr"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path

    settings = get_settings()
    tools_dir = Path(settings.comic_rar_tools_dir).expanduser()
    local_candidates = [
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
        tools_dir / "7z.exe",
        tools_dir / "7za.exe",
        tools_dir / "7zr.exe",
        tools_dir / "7z",
        tools_dir / "7za",
        tools_dir / "7zr",
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _extract_from_rar_with_7z(local_path: str, *, fmt: str) -> ComicExtractionResult:
    tool = _find_7z_tool()
    if not tool:
        raise ValueError("7z CLI not found for RAR fallback extraction")
    with tempfile.TemporaryDirectory(prefix="comic_rar_7z_") as extract_dir:
        extract_cmd = [tool, "x", "-y", f"-o{extract_dir}", local_path]
        extract_proc = subprocess.run(extract_cmd, capture_output=True, check=False)
        if extract_proc.returncode not in (0, 1):
            stderr = extract_proc.stderr.decode("utf-8", errors="ignore").strip()
            raise ValueError(f"7z extract failed: code={extract_proc.returncode} stderr={stderr}")

        root = Path(extract_dir)
        image_paths = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
        if not image_paths:
            stderr = extract_proc.stderr.decode("utf-8", errors="ignore").strip()
            raise ValueError(f"Archive has no image pages after 7z extract. stderr={stderr}")

        image_paths.sort(key=lambda path: path.relative_to(root).as_posix().lower())
        cover_path = image_paths[0]
        cover_bytes = cover_path.read_bytes()
        if not cover_bytes:
            raise ValueError(f"7z extracted empty cover file: {cover_path.name}")

        cover_member = cover_path.relative_to(root).as_posix()
        cover_extension = cover_path.suffix.lower().lstrip(".") or "jpg"
        return ComicExtractionResult(
            format=fmt,
            page_count=len(image_paths),
            cover_bytes=cover_bytes,
            cover_extension=cover_extension,
            details={"cover_member": cover_member, "backend": "7z_fallback"},
        )


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
        cover_name, page_count = _select_cover_and_count(image_names)
        with tempfile.TemporaryDirectory(prefix="comic_7z_cover_") as temp_dir:
            archive.extract(path=temp_dir, targets=[cover_name])
            cover_path = Path(temp_dir) / Path(cover_name)
            if not cover_path.exists():
                raise ValueError("Failed to extract 7Z cover image")
            cover_bytes = cover_path.read_bytes()
        cover_extension = Path(cover_name).suffix.lower().lstrip(".") or "jpg"
        return ComicExtractionResult(
            format=fmt,
            page_count=page_count,
            cover_bytes=cover_bytes,
            cover_extension=cover_extension,
            details={"cover_member": cover_name},
        )


def _select_cover_and_count(image_names: list[str]) -> tuple[str, int]:
    ordered = [name for name in image_names if name]
    ordered.sort(key=lambda value: value.lower())
    if not ordered:
        raise ValueError("Archive has no image pages")
    return ordered[0], len(ordered)


def _extract_from_epub(local_path: str) -> ComicExtractionResult:
    with zipfile.ZipFile(local_path, "r") as archive:
        names = set(archive.namelist())
        if "META-INF/container.xml" not in names:
            raise ValueError("EPUB missing META-INF/container.xml")

        container_xml = archive.read("META-INF/container.xml")
        container_root = ElementTree.fromstring(container_xml)
        rootfile = container_root.find(".//{*}rootfile")
        if rootfile is None:
            raise ValueError("EPUB container has no rootfile")
        opf_path = rootfile.attrib.get("full-path")
        if not opf_path or opf_path not in names:
            raise ValueError("EPUB OPF manifest not found")

        opf_xml = archive.read(opf_path)
        opf_root = ElementTree.fromstring(opf_xml)

        manifest_items = {}
        for item in opf_root.findall(".//{*}manifest/{*}item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            if item_id and href:
                manifest_items[item_id] = item.attrib

        spine_items = opf_root.findall(".//{*}spine/{*}itemref")
        page_count = len(spine_items) if spine_items else None

        opf_dir = posixpath.dirname(opf_path)
        cover_href = None

        cover_meta = opf_root.find(".//{*}metadata/{*}meta[@name='cover']")
        if cover_meta is not None:
            cover_id = cover_meta.attrib.get("content")
            cover_item = manifest_items.get(cover_id) if cover_id else None
            if cover_item is not None:
                cover_href = cover_item.get("href")

        if not cover_href:
            for item in opf_root.findall(".//{*}manifest/{*}item"):
                props = (item.attrib.get("properties") or "").lower()
                media = (item.attrib.get("media-type") or "").lower()
                if "cover-image" in props or media.startswith("image/"):
                    cover_href = item.attrib.get("href")
                    if cover_href:
                        break

        cover_bytes = None
        cover_extension = None
        resolved_cover_member = None
        if cover_href:
            cover_member = posixpath.normpath(posixpath.join(opf_dir, cover_href))
            if cover_member in names:
                cover_bytes = archive.read(cover_member)
                cover_extension = Path(cover_member).suffix.lower().lstrip(".") or "jpg"
                resolved_cover_member = cover_member

        if cover_bytes is None:
            image_names = [
                name
                for name in archive.namelist()
                if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_EXTENSIONS
            ]
            image_names.sort(key=lambda value: value.lower())
            if image_names:
                resolved_cover_member = image_names[0]
                cover_bytes = archive.read(resolved_cover_member)
                cover_extension = Path(resolved_cover_member).suffix.lower().lstrip(".") or "jpg"

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
            "cover": "extracted_from_embedded_image" if cover_bytes else "embedded_image_not_found",
            "cover_page_index": cover_page_index,
        },
    )


def optimize_cover_image(
    cover_bytes: bytes,
    cover_extension: str | None,
    *,
    max_width: int,
    max_height: int,
    target_bytes: int,
    quality_steps: tuple[int, ...],
) -> tuple[bytes, str, dict[str, Any]]:
    """Resize/compress cover image to reduce cloud storage while keeping quality."""
    original_size = len(cover_bytes)
    try:
        with Image.open(io.BytesIO(cover_bytes)) as src_image:
            image = ImageOps.exif_transpose(src_image)
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            best_bytes: bytes | None = None
            best_quality: int | None = None
            best_size = 2**31 - 1

            for quality in quality_steps:
                out = io.BytesIO()
                image.save(
                    out,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=True,
                )
                candidate = out.getvalue()
                candidate_size = len(candidate)
                if candidate_size < best_size:
                    best_bytes = candidate
                    best_size = candidate_size
                    best_quality = quality
                if candidate_size <= target_bytes:
                    break

            if best_bytes is None:
                return cover_bytes, (cover_extension or "jpg"), {
                    "cover_optimized": False,
                    "reason": "encode_failed",
                }

            return best_bytes, "jpg", {
                "cover_optimized": True,
                "cover_original_bytes": original_size,
                "cover_optimized_bytes": len(best_bytes),
                "cover_width": image.width,
                "cover_height": image.height,
                "cover_quality": best_quality,
            }
    except (UnidentifiedImageError, OSError):
        return cover_bytes, (cover_extension or "jpg"), {
            "cover_optimized": False,
            "reason": "unsupported_image",
            "cover_original_bytes": original_size,
        }


class ComicMetadataService:
    """Extract comic data and map into ItemMetadata values."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_linked_account(self, account_id: str | UUID | None) -> LinkedAccount | None:
        if account_id is None:
            return None
        pk: str | UUID = account_id
        if isinstance(pk, str):
            try:
                pk = UUID(pk)
            except ValueError:
                return None
        return await self.session.get(LinkedAccount, pk)

    async def process_item_ids(
        self,
        account_id,
        item_ids: list[str],
        *,
        job_id=None,
        batch_id=None,
        progress_reporter=None,
    ) -> dict[str, int]:
        account = await self.session.get(LinkedAccount, account_id)
        if not account:
            raise ValueError("Account not found")

        plugin_service = MetadataPluginService(self.session)
        category = await plugin_service.ensure_active_comic_category()
        attr_ids = await plugin_service.comic_attribute_id_map()
        plugin_settings = await PluginSettingsService(self.session).get_comic_runtime_settings()

        token_manager = TokenManager(self.session)
        client = build_drive_client(account, token_manager)
        target_account = account
        if plugin_settings.storage_account_id:
            maybe_target = await self._get_linked_account(plugin_settings.storage_account_id)
            if maybe_target:
                target_account = maybe_target
        target_client = build_drive_client(target_account, token_manager)

        files_to_process = await self._expand_items(client, account, item_ids)
        stats = {"total": len(files_to_process), "mapped": 0, "skipped": 0, "failed": 0}
        logger.info(
            "Comic mapping started account_id=%s selected_items=%s expanded_files=%s job_id=%s",
            account.id,
            len(item_ids),
            len(files_to_process),
            job_id,
        )
        if progress_reporter is not None:
            await progress_reporter.set_total(stats["total"])
        return await self._process_files(
            files_to_process=files_to_process,
            source_account=account,
            source_client=client,
            target_account=target_account,
            target_client=target_client,
            category_id=category.id,
            attr_ids=attr_ids,
            plugin_settings=plugin_settings,
            stats=stats,
            job_id=job_id,
            batch_id=batch_id,
            force_remap=False,
            progress_reporter=progress_reporter,
        )

    async def reindex_mapped_comics(self, *, job_id=None, batch_id=None) -> dict[str, int]:
        plugin_service = MetadataPluginService(self.session)
        category = await plugin_service.ensure_active_comic_category()
        stmt = select(ItemMetadata.account_id, ItemMetadata.item_id).where(ItemMetadata.category_id == category.id)
        result = await self.session.execute(stmt)
        rows = result.all()
        by_account: dict[Any, list[str]] = {}
        for account_id, item_id in rows:
            by_account.setdefault(account_id, []).append(item_id)
        if not by_account:
            return {"total": 0, "mapped": 0, "skipped": 0, "failed": 0, "accounts": 0}

        plugin_settings = await PluginSettingsService(self.session).get_comic_runtime_settings()
        overall = {"total": 0, "mapped": 0, "skipped": 0, "failed": 0, "accounts": len(by_account)}
        for account_id, item_ids in by_account.items():
            account = await self._get_linked_account(account_id)
            if not account:
                overall["failed"] += len(item_ids)
                overall["total"] += len(item_ids)
                continue

            plugin_service = MetadataPluginService(self.session)
            attr_ids = await plugin_service.comic_attribute_id_map()
            token_manager = TokenManager(self.session)
            source_client = build_drive_client(account, token_manager)
            target_account = account
            if plugin_settings.storage_account_id:
                maybe_target = await self._get_linked_account(plugin_settings.storage_account_id)
                if maybe_target:
                    target_account = maybe_target
            target_client = build_drive_client(target_account, token_manager)
            files_to_process = await self._expand_items(source_client, account, item_ids)
            stats = {"total": len(files_to_process), "mapped": 0, "skipped": 0, "failed": 0}
            stats = await self._process_files(
                files_to_process=files_to_process,
                source_account=account,
                source_client=source_client,
                target_account=target_account,
                target_client=target_client,
                category_id=category.id,
                attr_ids=attr_ids,
                plugin_settings=plugin_settings,
                stats=stats,
                job_id=job_id,
                batch_id=batch_id,
                force_remap=True,
            )
            overall["total"] += stats["total"]
            overall["mapped"] += stats["mapped"]
            overall["skipped"] += stats["skipped"]
            overall["failed"] += stats["failed"]
        return overall

    async def _process_files(
        self,
        *,
        files_to_process: list[Any],
        source_account: LinkedAccount,
        source_client: DriveProviderClient,
        target_account: LinkedAccount,
        target_client: DriveProviderClient,
        category_id,
        attr_ids: dict[str, str],
        plugin_settings: ComicRuntimeSettings,
        stats: dict[str, int],
        job_id,
        batch_id,
        force_remap: bool,
        progress_reporter=None,
    ) -> dict[str, int]:
        batch_size = COMIC_MAPPING_COMMIT_BATCH_SIZE
        processed_since_commit = 0
        source_account_pk = source_account.id
        source_account_id = str(source_account_pk)
        target_account_pk = target_account.id

        cover_folder_id = await self._ensure_cover_folder(
            target_client,
            target_account,
            parent_folder_id=plugin_settings.storage_parent_folder_id,
            cover_folder_name=plugin_settings.storage_folder_name,
        )
        for file_item in files_to_process:
            try:
                mapped = await self._process_single_file(
                    source_client=source_client,
                    source_account=source_account,
                    source_account_pk=source_account_pk,
                    source_account_id=source_account_id,
                    cover_client=target_client,
                    cover_account=target_account,
                    item=file_item,
                    cover_folder_id=cover_folder_id,
                    category_id=category_id,
                    attr_ids=attr_ids,
                    cover_settings=plugin_settings,
                    job_id=job_id,
                    batch_id=batch_id,
                    force_remap=force_remap,
                )
                if mapped:
                    stats["mapped"] += 1
                else:
                    stats["skipped"] += 1
                processed_since_commit += 1
                if processed_since_commit >= batch_size:
                    await self.session.commit()
                    processed_since_commit = 0
                    logger.info(
                        "Comic mapping batch committed account_id=%s mapped=%s skipped=%s failed=%s total=%s",
                        source_account_id,
                        stats["mapped"],
                        stats["skipped"],
                        stats["failed"],
                        stats["total"],
                    )
            except Exception:
                await self.session.rollback()
                refreshed_source = await self.session.get(LinkedAccount, source_account_pk)
                if refreshed_source is not None:
                    source_account = refreshed_source
                refreshed_target = await self.session.get(LinkedAccount, target_account_pk)
                if refreshed_target is not None:
                    target_account = refreshed_target
                stats["failed"] += 1
                logger.exception(
                    "Comic mapping failed for account=%s item=%s",
                    source_account_id,
                    getattr(file_item, "id", None),
                )
            finally:
                if progress_reporter is not None:
                    await progress_reporter.increment()
                    if progress_reporter.current % 5 == 0:
                        await progress_reporter.update_metrics(
                            mapped=stats["mapped"],
                            skipped=stats["skipped"],
                            failed=stats["failed"],
                        )

        if processed_since_commit > 0:
            await self.session.commit()

        if progress_reporter is not None:
            await progress_reporter.update_metrics(
                mapped=stats["mapped"],
                skipped=stats["skipped"],
                failed=stats["failed"],
            )

        logger.info(
            "Comic mapping completed account_id=%s mapped=%s skipped=%s failed=%s total=%s",
            source_account_id,
            stats["mapped"],
            stats["skipped"],
            stats["failed"],
            stats["total"],
        )
        return stats

    async def _expand_items(
        self,
        client: DriveProviderClient,
        account: LinkedAccount,
        item_ids: list[str],
    ) -> list[Any]:
        collected: dict[str, Any] = {}
        for item_id in item_ids:
            item = await client.get_item_metadata(account, item_id)
            if item.item_type == "folder":
                await self._collect_folder_files(client, account, item.id, collected)
            else:
                collected[item.id] = item
        return list(collected.values())

    async def _collect_folder_files(
        self,
        client: DriveProviderClient,
        account: LinkedAccount,
        folder_id: str,
        collected: dict[str, Any],
    ) -> None:
        listing = await client.list_folder_items(account, folder_id)
        while True:
            for item in listing.items:
                if item.item_type == "folder":
                    await self._collect_folder_files(client, account, item.id, collected)
                else:
                    collected[item.id] = item

            if not listing.next_link:
                break
            listing = await client.list_items_by_next_link(account, listing.next_link)

    async def _ensure_cover_folder(
        self,
        client: DriveProviderClient,
        account: LinkedAccount,
        *,
        parent_folder_id: str,
        cover_folder_name: str,
    ) -> str:
        if parent_folder_id == "root":
            listing = await client.list_root_items(account)
        else:
            listing = await client.list_folder_items(account, parent_folder_id)
        for item in listing.items:
            if item.item_type == "folder" and item.name == cover_folder_name:
                return item.id

        folder = await client.create_folder(
            account,
            cover_folder_name,
            parent_id=parent_folder_id,
            conflict_behavior="rename",
        )
        return folder.id

    async def _process_single_file(
        self,
        *,
        source_client: DriveProviderClient,
        source_account: LinkedAccount,
        source_account_pk,
        source_account_id: str,
        cover_client: DriveProviderClient,
        cover_account: LinkedAccount,
        item: Any,
        cover_folder_id: str,
        category_id,
        attr_ids: dict[str, str],
        cover_settings: ComicRuntimeSettings,
        job_id,
        batch_id,
        force_remap: bool,
    ) -> bool:
        ext = file_extension(item.name)
        if ext not in SUPPORTED_COMIC_EXTENSIONS:
            return False
        if not force_remap and await self._is_already_mapped(
            account_id=source_account_pk,
            item_id=item.id,
            category_id=category_id,
            attr_ids=attr_ids,
        ):
            return False

        temp_dir = tempfile.mkdtemp(prefix="comic_extract_")
        local_path = str(Path(temp_dir) / f"{item.id}.{ext or 'bin'}")
        try:
            await source_client.download_file_to_path(source_account, item.id, local_path)
            extraction = extract_comic_asset(local_path, ext)
            mapped_values = self._build_metadata_values(item=item, extraction=extraction, attr_ids=attr_ids)

            if extraction.cover_bytes:
                optimized_cover, cover_ext, optimize_details = optimize_cover_image(
                    extraction.cover_bytes,
                    extraction.cover_extension,
                    max_width=cover_settings.max_width,
                    max_height=cover_settings.max_height,
                    target_bytes=cover_settings.target_bytes,
                    quality_steps=cover_settings.quality_steps,
                )
                upload_name = f"{item.id}.{cover_ext}"
                uploaded = await cover_client.upload_small_file(
                    cover_account,
                    upload_name,
                    optimized_cover,
                    cover_folder_id,
                )
                cover_id_attr = attr_ids.get("cover_item_id")
                cover_account_attr = attr_ids.get("cover_account_id")
                cover_name_attr = attr_ids.get("cover_filename")
                if cover_id_attr:
                    mapped_values[cover_id_attr] = uploaded.id
                if cover_account_attr:
                    mapped_values[cover_account_attr] = str(cover_account.id)
                if cover_name_attr:
                    mapped_values[cover_name_attr] = uploaded.name
                extraction.details.update(optimize_details)

            await apply_metadata_change(
                self.session,
                account_id=source_account_pk,
                item_id=item.id,
                category_id=category_id,
                values=mapped_values,
                batch_id=batch_id,
                job_id=job_id,
            )
            return True
        except ValueError as exc:
            # Non-comic/unsupported content inside accepted container types should be skipped.
            non_comic_markers = (
                "archive has no image pages",
                "epub has no cover image",
                "epub missing",
                "epub container has no rootfile",
                "epub opf manifest not found",
            )
            error_text = str(exc).lower()
            if any(marker in error_text for marker in non_comic_markers):
                logger.info(
                    "Skipping non-comic item account=%s item=%s name=%s reason=%s",
                    source_account_id,
                    item.id,
                    item.name,
                    exc,
                )
                return False
            raise
        finally:
            try:
                Path(local_path).unlink(missing_ok=True)
                Path(temp_dir).rmdir()
            except Exception:
                pass

    def _build_metadata_values(self, *, item: Any, extraction: ComicExtractionResult, attr_ids: dict[str, str]) -> dict[str, Any]:
        values: dict[str, Any] = {}

        def set_if_exists(field_key: str, value: Any) -> None:
            attr_id = attr_ids.get(field_key)
            if attr_id and value is not None:
                values[attr_id] = value

        stem = Path(item.name).stem
        set_if_exists("title", stem)
        set_if_exists("file_format", extraction.format)
        set_if_exists("page_count", extraction.page_count)
        return values

    async def _is_already_mapped(self, *, account_id, item_id: str, category_id, attr_ids: dict[str, str]) -> bool:
        stmt = select(ItemMetadata).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.item_id == item_id,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is None or existing.category_id != category_id:
            return False

        values = existing.values or {}
        check_fields = ("cover_item_id", "cover_account_id", "page_count", "file_format", "title")
        for field_key in check_fields:
            attr_id = attr_ids.get(field_key)
            if not attr_id:
                continue
            value = values.get(attr_id)
            if value is not None and value != "":
                return True
        return False
