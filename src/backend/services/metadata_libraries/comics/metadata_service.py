"""Comic extraction and metadata mapping helpers."""

from __future__ import annotations

import io
import inspect
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.drive.transfer_service import DriveTransferService
from backend.common.error_items import ErrorItemsCollector
from backend.core.config import get_settings
from backend.core.exceptions import DriveOrganizerError
from backend.db.models import ItemMetadata, LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.item_index import parent_id_from_breadcrumb
from backend.services.metadata_libraries.comics import archive_reader
from backend.services.metadata_libraries.comics.archive_reader import (
    ComicExtractionResult,
    SUPPORTED_COMIC_EXTENSIONS,
    file_extension,
    is_non_comic_extraction_error,
    _pick_first_non_empty_payload,
    _rar_cli_subprocess_env,
    _temporary_rar_cli_locale,
)
from backend.services.metadata_libraries.implementations.comics.schema import (
    COMICS_LIBRARY_KEY,
)
from backend.services.metadata_libraries.service import MetadataLibraryService
from backend.services.metadata_libraries.settings import (
    ComicsRuntimeSettings,
    MetadataLibrarySettingsService,
)
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
logger = logging.getLogger(__name__)
COMIC_MAPPING_COMMIT_BATCH_SIZE = 10
COMIC_DOWNLOAD_BASE_TIMEOUT_SECONDS = 120.0
COMIC_DOWNLOAD_MAX_TIMEOUT_SECONDS = 1800.0
COMIC_DOWNLOAD_BYTES_PER_SECOND = (
    1.5 * 1024 * 1024
)  # 1.5 MB/s baseline for timeout scaling.
COMIC_ERROR_ITEMS_LIMIT = 50


@dataclass(slots=True)
class IndexedComicItem:
    """Indexed file descriptor used by background comic mapping jobs."""

    id: str
    name: str
    extension: str | None = None
    item_type: str = "file"
    size: int | None = None


@dataclass(slots=True)
class ComicProcessOutcome:
    """Result of processing one comic item."""

    mapped: bool
    skip_reason: str | None = None
    skip_stage: str | None = None


def _is_non_comic_extraction_error(error_text: str) -> bool:
    return is_non_comic_extraction_error(error_text)


_extract_from_zip = archive_reader._extract_from_zip
_extract_from_tar = archive_reader._extract_from_tar
_extract_from_pdf = archive_reader._extract_from_pdf
_extract_from_epub = archive_reader._extract_from_epub
_extract_from_7z = archive_reader._extract_from_7z
_detect_archive_container = archive_reader._detect_archive_container
ensure_rar_backend = archive_reader.ensure_rar_backend


def _find_rar_cli_tools() -> list[tuple[str, str]]:
    settings = get_settings()
    candidates: list[tuple[str, str]] = []
    explicit_tool = getattr(settings, "comic_rar_tool_path", None)
    tools_dir_raw = getattr(settings, "comic_rar_tools_dir", None)

    if explicit_tool:
        explicit_path = Path(explicit_tool).expanduser()
        if explicit_path.exists():
            tool_name = explicit_path.name.lower()
            if tool_name.startswith("unar"):
                candidates.append((str(explicit_path), "unar"))
            elif tool_name.startswith("unrar"):
                candidates.append((str(explicit_path), "unrar"))
            else:
                candidates.append((str(explicit_path), "7z"))

    if tools_dir_raw:
        tools_dir = Path(tools_dir_raw).expanduser()
        for name, kind in (
            ("unar", "unar"),
            ("unar.exe", "unar"),
            ("unrar", "unrar"),
            ("unrar.exe", "unrar"),
            ("7z", "7z"),
            ("7z.exe", "7z"),
        ):
            candidate = tools_dir / name
            if candidate.exists():
                candidates.append((str(candidate), kind))

    for name, kind in (
        ("unar", "unar"),
        ("unar.exe", "unar"),
        ("unrar", "unrar"),
        ("unrar.exe", "unrar"),
        ("7z", "7z"),
        ("7z.exe", "7z"),
    ):
        resolved = shutil.which(name)
        if resolved:
            candidates.append((resolved, kind))

    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tool, kind in candidates:
        if tool in seen:
            continue
        seen.add(tool)
        unique.append((tool, kind))
    return unique


def _extract_from_rar_with_7z(local_path: str, *, fmt: str) -> ComicExtractionResult:
    failures: list[str] = []
    tools = _find_rar_cli_tools()
    if not tools:
        return archive_reader._extract_from_rar_with_7z(local_path, fmt=fmt)

    for tool, kind in tools:
        with tempfile.TemporaryDirectory(prefix="comic_rar_cli_") as extract_dir:
            if kind == "unar":
                command = [
                    tool,
                    "-force-overwrite",
                    "-output-directory",
                    extract_dir,
                    local_path,
                ]
            elif kind == "unrar":
                command = [tool, "x", "-idq", "-o+", local_path, extract_dir]
            else:
                return archive_reader._extract_from_rar_with_7z(local_path, fmt=fmt)

            process = subprocess.run(
                command,
                capture_output=True,
                check=False,
                env=_rar_cli_subprocess_env(),
            )
            stderr = process.stderr.decode("utf-8", errors="ignore").strip()
            root = Path(extract_dir)
            image_paths = [
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in archive_reader.IMAGE_EXTENSIONS
            ]
            image_paths.sort(key=lambda path: path.relative_to(root).as_posix().lower())
            cover_path = next((path for path in image_paths if path.stat().st_size > 0), None)
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
                        "cli_return_code": process.returncode,
                        "cli_stderr": stderr[:2000] if stderr else "",
                    },
                )
            failures.append(
                f"{Path(tool).name}: code={process.returncode} stderr={stderr[:400]}"
            )

    raise ValueError(
        "RAR CLI extraction failed across available tools: "
        + " | ".join(failures[:4])
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
                    and Path(info.filename).suffix.lower()
                    in archive_reader.IMAGE_EXTENSIONS
                ]
                ordered_names, page_count = archive_reader._ordered_image_names_and_count(
                    image_names
                )
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
        if any(marker in error_text for marker in archive_reader.RAR_BACKEND_FAILURE_MARKERS):
            logger.warning(
                "RAR Python backend failed for %s (%s). Trying CLI fallback.",
                local_path,
                exc,
            )
            return _extract_from_rar_with_7z(local_path, fmt=fmt)
        raise


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
                local_path,
                fmt=fmt,
                container=container,
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
    """Compatibility wrapper so legacy tests can patch module-level helpers."""
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
    if ext == "pdf":
        return _extract_from_pdf(local_path)
    if ext == "epub":
        return _extract_from_epub(local_path)
    raise ValueError(f"Unsupported comic extension: {ext}")


def _existing_comic_mapping_skip_reason(
    existing: ItemMetadata | None,
    *,
    category_id: UUID,
    attr_ids: dict[str, str],
) -> str | None:
    if existing is None:
        return None
    if existing.category_id != category_id:
        return "Item already mapped to another metadata category"

    values = existing.values or {}
    check_fields = (
        "cover_item_id",
        "cover_account_id",
        "page_count",
        "file_format",
    )
    for field_key in check_fields:
        attr_id = attr_ids.get(field_key)
        if not attr_id:
            continue
        value = values.get(attr_id)
        if value is not None and value != "":
            return "Item already mapped"
    return None


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
                return (
                    cover_bytes,
                    (cover_extension or "jpg"),
                    {
                        "cover_optimized": False,
                        "reason": "encode_failed",
                    },
                )

            return (
                best_bytes,
                "jpg",
                {
                    "cover_optimized": True,
                    "cover_original_bytes": original_size,
                    "cover_optimized_bytes": len(best_bytes),
                    "cover_width": image.width,
                    "cover_height": image.height,
                    "cover_quality": best_quality,
                },
            )
    except (UnidentifiedImageError, OSError):
        return (
            cover_bytes,
            (cover_extension or "jpg"),
            {
                "cover_optimized": False,
                "reason": "unsupported_image",
                "cover_original_bytes": original_size,
            },
        )


class ComicMetadataService:
    """Extract comic data and map into ItemMetadata values."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the service with a database session."""
        self.session = session

    @staticmethod
    def _init_stats(total: int, *, accounts: int | None = None) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "total": total,
            "mapped": 0,
            "skipped": 0,
            "failed": 0,
            "error_items": [],
            "error_items_truncated": 0,
        }
        if accounts is not None:
            stats["accounts"] = accounts
        return stats

    @staticmethod
    def _record_error_item(
        stats: dict[str, Any],
        *,
        reason: str,
        item_id: str | None = None,
        item_name: str | None = None,
        account_id: str | None = None,
        stage: str | None = None,
    ) -> None:
        collector = ErrorItemsCollector(stats, limit=COMIC_ERROR_ITEMS_LIMIT)
        collector.record(
            reason=reason,
            item_id=item_id,
            item_name=item_name,
            account_id=account_id,
            stage=stage,
        )

    @classmethod
    def _merge_error_items(cls, target: dict[str, Any], source: dict[str, Any]) -> None:
        collector = ErrorItemsCollector(target, limit=COMIC_ERROR_ITEMS_LIMIT)
        collector.merge(source)

    async def _get_linked_account(
        self, account_id: str | UUID | None
    ) -> LinkedAccount | None:
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
        initialize_progress_total: bool = True,
    ) -> dict[str, Any]:
        """Extract and map metadata for item ids and nested folder contents."""
        account = await self.session.get(LinkedAccount, account_id)
        if not account:
            raise ValueError("Account not found")

        library_service = MetadataLibraryService(self.session)
        category = await library_service.require_active_comics_category()
        attr_ids = await library_service.comics_attribute_id_map(ensure_schema=False)
        plugin_settings = await MetadataLibrarySettingsService(
            self.session
        ).get_comics_runtime_settings()

        token_manager = TokenManager(self.session)
        client = build_drive_client(account, token_manager)
        target_account = account
        if plugin_settings.storage_account_id:
            maybe_target = await self._get_linked_account(
                plugin_settings.storage_account_id
            )
            if maybe_target:
                target_account = maybe_target
        target_client = build_drive_client(target_account, token_manager)

        files_to_process = await self._expand_items(client, account, item_ids)
        stats = self._init_stats(len(files_to_process))
        logger.info(
            "Comic mapping started account_id=%s selected_items=%s expanded_files=%s job_id=%s",
            account.id,
            len(item_ids),
            len(files_to_process),
            job_id,
        )
        if progress_reporter is not None and initialize_progress_total:
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

    async def process_indexed_items(
        self,
        account_id,
        files_to_process: list[IndexedComicItem],
        *,
        job_id=None,
        batch_id=None,
        progress_reporter=None,
        initialize_progress_total: bool = True,
        force_remap: bool = False,
    ) -> dict[str, Any]:
        """Extract and map metadata for pre-indexed comic file entries."""
        account = await self.session.get(LinkedAccount, account_id)
        if not account:
            raise ValueError("Account not found")

        library_service = MetadataLibraryService(self.session)
        category = await library_service.require_active_comics_category()
        attr_ids = await library_service.comics_attribute_id_map(ensure_schema=False)
        plugin_settings = await MetadataLibrarySettingsService(
            self.session
        ).get_comics_runtime_settings()

        token_manager = TokenManager(self.session)
        client = build_drive_client(account, token_manager)
        target_account = account
        if plugin_settings.storage_account_id:
            maybe_target = await self._get_linked_account(
                plugin_settings.storage_account_id
            )
            if maybe_target:
                target_account = maybe_target
        target_client = build_drive_client(target_account, token_manager)

        stats = self._init_stats(len(files_to_process))
        logger.info(
            "Comic mapping started (indexed) account_id=%s selected_items=%s expanded_files=%s job_id=%s",
            account.id,
            len(files_to_process),
            len(files_to_process),
            job_id,
        )
        if progress_reporter is not None and initialize_progress_total:
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
            force_remap=force_remap,
            progress_reporter=progress_reporter,
        )

    async def reindex_mapped_comics(
        self, *, job_id=None, batch_id=None
    ) -> dict[str, Any]:
        """Re-map all already-tagged comics using current runtime settings."""
        library_service = MetadataLibraryService(self.session)
        category = await library_service.require_active_comics_category()
        stmt = select(ItemMetadata.account_id, ItemMetadata.item_id).where(
            ItemMetadata.category_id == category.id
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        by_account: dict[Any, list[str]] = {}
        for account_id, item_id in rows:
            by_account.setdefault(account_id, []).append(item_id)
        if not by_account:
            return self._init_stats(0, accounts=0)

        plugin_settings = await MetadataLibrarySettingsService(
            self.session
        ).get_comics_runtime_settings()
        overall = self._init_stats(0, accounts=len(by_account))
        for account_id, item_ids in by_account.items():
            account = await self._get_linked_account(account_id)
            if not account:
                overall["failed"] += len(item_ids)
                overall["total"] += len(item_ids)
                self._record_error_item(
                    overall,
                    reason=f"Linked account {account_id} not found",
                    account_id=str(account_id),
                )
                continue

            library_service = MetadataLibraryService(self.session)
            attr_ids = await library_service.comics_attribute_id_map(
                ensure_schema=False
            )
            token_manager = TokenManager(self.session)
            source_client = build_drive_client(account, token_manager)
            target_account = account
            if plugin_settings.storage_account_id:
                maybe_target = await self._get_linked_account(
                    plugin_settings.storage_account_id
                )
                if maybe_target:
                    target_account = maybe_target
            target_client = build_drive_client(target_account, token_manager)
            files_to_process = await self._expand_items(
                source_client, account, item_ids
            )
            stats = self._init_stats(len(files_to_process))
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
            self._merge_error_items(overall, stats)
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
        plugin_settings: ComicsRuntimeSettings,
        stats: dict[str, Any],
        job_id,
        batch_id,
        force_remap: bool,
        progress_reporter=None,
    ) -> dict[str, Any]:
        batch_size = COMIC_MAPPING_COMMIT_BATCH_SIZE
        processed_since_commit = 0
        source_account_pk = source_account.id
        source_account_id = str(source_account_pk)
        target_account_pk = target_account.id

        cover_folder_id = await self._resolve_cover_folder_id(
            client=target_client,
            account=target_account,
            plugin_settings=plugin_settings,
        )
        existing_metadata_by_item_id = await self._load_existing_metadata_values(
            account_id=source_account_pk,
            item_ids=[
                str(getattr(file_item, "id", ""))
                for file_item in files_to_process
                if str(getattr(file_item, "id", "")).strip()
            ],
            category_id=category_id,
        )
        for file_item in files_to_process:
            try:
                outcome = await self._process_single_file(
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
                    existing_metadata_values=existing_metadata_by_item_id.get(
                        str(getattr(file_item, "id", ""))
                    ),
                )
                if outcome.mapped:
                    stats["mapped"] += 1
                else:
                    stats["skipped"] += 1
                    if outcome.skip_reason:
                        self._record_error_item(
                            stats,
                            reason=outcome.skip_reason,
                            item_id=getattr(file_item, "id", None),
                            item_name=getattr(file_item, "name", None),
                            account_id=source_account_id,
                            stage=outcome.skip_stage,
                        )
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
            except Exception as exc:
                await self.session.rollback()
                refreshed_source = await self.session.get(
                    LinkedAccount, source_account_pk
                )
                if refreshed_source is not None:
                    source_account = refreshed_source
                refreshed_target = await self.session.get(
                    LinkedAccount, target_account_pk
                )
                if refreshed_target is not None:
                    target_account = refreshed_target
                stats["failed"] += 1
                self._record_error_item(
                    stats,
                    reason=str(exc),
                    item_id=getattr(file_item, "id", None),
                    item_name=getattr(file_item, "name", None),
                    account_id=source_account_id,
                )
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
                            error_items=stats.get("error_items", []),
                            error_items_truncated=stats.get("error_items_truncated", 0),
                        )

        if processed_since_commit > 0:
            await self.session.commit()

        if progress_reporter is not None:
            await progress_reporter.update_metrics(
                mapped=stats["mapped"],
                skipped=stats["skipped"],
                failed=stats["failed"],
                error_items=stats.get("error_items", []),
                error_items_truncated=stats.get("error_items_truncated", 0),
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
                    await self._collect_folder_files(
                        client, account, item.id, collected
                    )
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
        while True:
            for item in listing.items:
                if item.item_type == "folder" and item.name == cover_folder_name:
                    return item.id
            if not listing.next_link:
                break
            listing = await client.list_items_by_next_link(account, listing.next_link)

        folder = await client.create_folder(
            account,
            cover_folder_name,
            parent_id=parent_folder_id,
            conflict_behavior="rename",
        )
        return folder.id

    async def _resolve_cover_folder_id(
        self,
        *,
        client: DriveProviderClient,
        account: LinkedAccount,
        plugin_settings: ComicsRuntimeSettings,
    ) -> str:
        configured_folder_id = str(
            getattr(plugin_settings, "storage_folder_id", None) or ""
        ).strip()
        is_persistable_target = (
            getattr(plugin_settings, "storage_account_id", None) is not None
            and str(account.id) == str(getattr(plugin_settings, "storage_account_id"))
        )
        if configured_folder_id and is_persistable_target:
            try:
                item = await client.get_item_metadata(account, configured_folder_id)
            except DriveOrganizerError as exc:
                if exc.status_code != 404:
                    raise
            else:
                if (
                    item.item_type == "folder"
                    and item.name == plugin_settings.storage_folder_name
                ):
                    return item.id

        cover_folder_id = await self._ensure_cover_folder(
            client,
            account,
            parent_folder_id=plugin_settings.storage_parent_folder_id,
            cover_folder_name=plugin_settings.storage_folder_name,
        )
        if is_persistable_target:
            await MetadataLibrarySettingsService(
                self.session
            ).persist_cover_storage_folder_id(
                COMICS_LIBRARY_KEY,
                folder_id=cover_folder_id,
            )
        return cover_folder_id

    async def _load_existing_metadata_values(
        self,
        *,
        account_id,
        item_ids: list[str],
        category_id,
    ) -> dict[str, dict[str, Any]]:
        if not item_ids:
            return {}
        stmt = select(ItemMetadata.item_id, ItemMetadata.values).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.category_id == category_id,
            ItemMetadata.item_id.in_(item_ids),
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        if inspect.isawaitable(rows):
            rows = await rows
        return {
            str(item_id): dict(values or {})
            for item_id, values in rows
            if str(item_id).strip()
        }

    async def _maybe_reuse_or_move_existing_cover(
        self,
        *,
        source_account_pk,
        item_id: str,
        cover_client: DriveProviderClient,
        cover_account: LinkedAccount,
        cover_folder_id: str,
        attr_ids: dict[str, str],
        existing_metadata_values: dict[str, Any] | None,
        category_id,
        job_id,
        batch_id,
    ) -> ComicProcessOutcome | None:
        _ = category_id
        cover_id_attr = attr_ids.get("cover_item_id")
        cover_account_attr = attr_ids.get("cover_account_id")
        cover_name_attr = attr_ids.get("cover_filename")
        if not cover_id_attr or not cover_account_attr or not existing_metadata_values:
            return None

        existing_cover_item_id = str(
            existing_metadata_values.get(cover_id_attr) or ""
        ).strip()
        existing_cover_account_id = str(
            existing_metadata_values.get(cover_account_attr) or ""
        ).strip()
        if not existing_cover_item_id or not existing_cover_account_id:
            return None

        try:
            existing_cover_account = await self._get_linked_account(
                UUID(existing_cover_account_id)
            )
        except ValueError:
            return None
        if existing_cover_account is None:
            return None

        existing_cover_client = build_drive_client(
            existing_cover_account, TokenManager(self.session)
        )
        existing_cover_name = (
            str(existing_metadata_values.get(cover_name_attr) or "").strip()
            if cover_name_attr
            else ""
        )

        if str(existing_cover_account.id) == str(cover_account.id):
            try:
                breadcrumb = await existing_cover_client.get_item_path(
                    existing_cover_account, existing_cover_item_id
                )
            except DriveOrganizerError as exc:
                if exc.status_code == 404:
                    return None
                raise

            if (parent_id_from_breadcrumb(breadcrumb) or "root") == cover_folder_id:
                return ComicProcessOutcome(
                    mapped=False,
                    skip_reason="Cover already indexed in target location",
                    skip_stage="cover_target",
                )

            moved_item = await existing_cover_client.update_item(
                existing_cover_account,
                existing_cover_item_id,
                parent_id=cover_folder_id,
            )
        else:
            if not existing_cover_name:
                try:
                    existing_cover_meta = await existing_cover_client.get_item_metadata(
                        existing_cover_account, existing_cover_item_id
                    )
                except DriveOrganizerError as exc:
                    if exc.status_code == 404:
                        return None
                    raise
                existing_cover_name = existing_cover_meta.name

            moved_cover_item_id = await DriveTransferService().transfer_file_between_accounts(
                source_client=existing_cover_client,
                destination_client=cover_client,
                source_account=existing_cover_account,
                destination_account=cover_account,
                source_item_id=existing_cover_item_id,
                source_item_name=existing_cover_name or existing_cover_item_id,
                destination_folder_id=cover_folder_id,
            )
            if not moved_cover_item_id:
                raise RuntimeError("Cover transfer did not return destination item id")
            moved_item = await cover_client.get_item_metadata(
                cover_account, moved_cover_item_id
            )

        moved_values = dict(existing_metadata_values)
        moved_values[cover_id_attr] = moved_item.id
        moved_values[cover_account_attr] = str(cover_account.id)
        if cover_name_attr:
            moved_values[cover_name_attr] = moved_item.name
        await apply_metadata_change(
            self.session,
            account_id=source_account_pk,
            item_id=item_id,
            category_id=category_id,
            values=moved_values,
            batch_id=batch_id,
            job_id=job_id,
        )
        return ComicProcessOutcome(mapped=True)

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
        cover_settings: ComicsRuntimeSettings,
        job_id,
        batch_id,
        force_remap: bool,
        existing_metadata_values: dict[str, Any] | None = None,
    ) -> ComicProcessOutcome:
        ext = (getattr(item, "extension", None) or file_extension(item.name)).lower()
        if ext not in SUPPORTED_COMIC_EXTENSIONS:
            return ComicProcessOutcome(
                mapped=False,
                skip_reason=f"Unsupported comic extension: {ext or 'none'}",
                skip_stage="extension_filter",
            )
        if not force_remap:
            skip_reason = await self._existing_mapping_skip_reason(
                account_id=source_account_pk,
                item_id=item.id,
                category_id=category_id,
                attr_ids=attr_ids,
            )
            if skip_reason:
                return ComicProcessOutcome(
                    mapped=False,
                    skip_reason=skip_reason,
                    skip_stage="existing_metadata",
                )
        else:
            relocated_outcome = await self._maybe_reuse_or_move_existing_cover(
                source_account_pk=source_account_pk,
                item_id=item.id,
                cover_client=cover_client,
                cover_account=cover_account,
                cover_folder_id=cover_folder_id,
                attr_ids=attr_ids,
                existing_metadata_values=existing_metadata_values,
                category_id=category_id,
                job_id=job_id,
                batch_id=batch_id,
            )
            if relocated_outcome is not None:
                return relocated_outcome

        temp_dir = tempfile.mkdtemp(prefix="comic_extract_")
        local_path = str(Path(temp_dir) / f"{item.id}.{ext or 'bin'}")
        try:
            download_timeout = self._download_timeout_for_item(item)
            await source_client.download_file_to_path(
                source_account,
                item.id,
                local_path,
                timeout_seconds=download_timeout,
            )
            extraction = extract_comic_asset(local_path, ext)
            mapped_values = self._build_metadata_values(
                item=item, extraction=extraction, attr_ids=attr_ids
            )

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

            mapped_values = self._merge_library_mapped_values(
                existing_metadata_values=existing_metadata_values,
                mapped_values=mapped_values,
            )

            await apply_metadata_change(
                self.session,
                account_id=source_account_pk,
                item_id=item.id,
                category_id=category_id,
                values=mapped_values,
                batch_id=batch_id,
                job_id=job_id,
            )
            return ComicProcessOutcome(mapped=True)
        except ValueError as exc:
            # Non-comic/unsupported content inside accepted container types should be skipped.
            error_text = str(exc).lower()
            if _is_non_comic_extraction_error(error_text):
                reason = f"Skipped non-comic content: {exc}"
                logger.info(
                    "Skipping non-comic item account=%s item=%s name=%s reason=%s",
                    source_account_id,
                    item.id,
                    item.name,
                    exc,
                )
                return ComicProcessOutcome(
                    mapped=False,
                    skip_reason=reason,
                    skip_stage="extract_comic",
                )
            raise
        finally:
            try:
                Path(local_path).unlink(missing_ok=True)
                Path(temp_dir).rmdir()
            except Exception:
                pass

    @staticmethod
    def _download_timeout_for_item(item: Any) -> float:
        raw_size = getattr(item, "size", None)
        try:
            size_bytes = int(raw_size) if raw_size is not None else 0
        except (TypeError, ValueError):
            size_bytes = 0

        if size_bytes <= 0:
            return COMIC_DOWNLOAD_BASE_TIMEOUT_SECONDS

        estimated_seconds = size_bytes / COMIC_DOWNLOAD_BYTES_PER_SECOND
        timeout = COMIC_DOWNLOAD_BASE_TIMEOUT_SECONDS + estimated_seconds
        return min(
            COMIC_DOWNLOAD_MAX_TIMEOUT_SECONDS,
            max(COMIC_DOWNLOAD_BASE_TIMEOUT_SECONDS, timeout),
        )

    def _build_metadata_values(
        self, *, item: Any, extraction: ComicExtractionResult, attr_ids: dict[str, str]
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}

        def set_if_exists(field_key: str, value: Any) -> None:
            attr_id = attr_ids.get(field_key)
            if attr_id and value is not None:
                values[attr_id] = value

        set_if_exists("file_format", extraction.format)
        set_if_exists("page_count", extraction.page_count)
        return values

    @staticmethod
    def _merge_library_mapped_values(
        *,
        existing_metadata_values: dict[str, Any] | None,
        mapped_values: dict[str, Any],
    ) -> dict[str, Any]:
        if not existing_metadata_values:
            return mapped_values
        merged_values = dict(existing_metadata_values)
        merged_values.update(mapped_values)
        return merged_values

    async def _existing_mapping_skip_reason(
        self, *, account_id, item_id: str, category_id, attr_ids: dict[str, str]
    ) -> str | None:
        stmt = select(ItemMetadata).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.item_id == item_id,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        return _existing_comic_mapping_skip_reason(
            existing,
            category_id=category_id,
            attr_ids=attr_ids,
        )
