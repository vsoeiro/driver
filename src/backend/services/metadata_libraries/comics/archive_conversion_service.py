"""Comic archive conversion workflow for indexed library items."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.drive.transfer_service import DriveTransferService
from backend.common.error_items import ErrorItemsCollector
from backend.db.models import LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.item_index import (
    build_item_path,
    delete_item_and_descendants,
    upsert_item_record,
)
from backend.services.metadata_libraries.comics.archive_reader import (
    _rar_cli_subprocess_env,
    _temporary_rar_cli_locale,
)
from backend.services.providers.factory import build_drive_client

CONVERSION_ERROR_ITEMS_LIMIT = 50
ZIP_LIKE_EXTENSIONS = {"zip", "cbz"}
RAR_LIKE_EXTENSIONS = {"rar", "cbr"}
SUPPORTED_CONVERSION_TARGETS = {"cbz", "cbr"}
ALLOWED_CONVERSIONS = {
    ("rar", "cbr"),
    ("rar", "cbz"),
    ("zip", "cbr"),
    ("zip", "cbz"),
    ("cbz", "cbr"),
    ("cbr", "cbz"),
}


@dataclass(slots=True)
class IndexedArchiveItem:
    id: str
    name: str
    extension: str | None
    item_type: str
    parent_id: str | None = None
    path: str | None = None
    size: int | None = None


def normalize_archive_format(value: str) -> str:
    normalized = str(value or "").strip().lower().lstrip(".")
    if normalized not in {"zip", "rar", "cbz", "cbr"}:
        raise ValueError(f"Unsupported archive format: {value}")
    return normalized


def validate_archive_conversion(source_format: str, target_format: str) -> tuple[str, str]:
    normalized_source = normalize_archive_format(source_format)
    normalized_target = normalize_archive_format(target_format)
    if normalized_target not in SUPPORTED_CONVERSION_TARGETS:
        raise ValueError("Target format must be cbz or cbr")
    if (normalized_source, normalized_target) not in ALLOWED_CONVERSIONS:
        raise ValueError(
            f"Unsupported archive conversion: {normalized_source} -> {normalized_target}"
        )
    return normalized_source, normalized_target


def source_extensions_for_format(source_format: str) -> tuple[str, ...]:
    normalized_source = normalize_archive_format(source_format)
    if normalized_source == "zip":
        return ("zip",)
    if normalized_source == "rar":
        return ("rar",)
    return (normalized_source,)


def _parent_path(item_path: str | None) -> str:
    normalized = str(item_path or "").strip()
    if not normalized or normalized == "/":
        return "/"
    if "/" not in normalized.rstrip("/"):
        return "/"
    parent = normalized.rsplit("/", 1)[0]
    return parent or "/"


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


def _extract_zip_archive(local_path: str, destination_dir: str) -> int:
    extracted = 0
    with zipfile.ZipFile(local_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = _normalize_member_parts(info.filename)
            if not parts:
                continue
            target_path = Path(destination_dir, *parts)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
            extracted += 1
    if extracted == 0:
        raise ValueError("Archive has no extractable files")
    return extracted


def _extract_rar_archive(local_path: str, destination_dir: str) -> int:
    try:
        import rarfile  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError("RAR support requires optional dependency 'rarfile'") from exc

    extracted = 0
    with _temporary_rar_cli_locale():
        with rarfile.RarFile(local_path, "r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                parts = _normalize_member_parts(info.filename)
                if not parts:
                    continue
                payload = archive.read(info.filename)
                target_path = Path(destination_dir, *parts)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(payload)
                extracted += 1
    if extracted == 0:
        raise ValueError("Archive has no extractable files")
    return extracted


def _create_cbz_archive(source_dir: str, target_path: str) -> int:
    written = 0
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(Path(source_dir).rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, arcname=path.relative_to(source_dir).as_posix())
            written += 1
    if written == 0:
        raise ValueError("No files available to package as CBZ")
    return written


def _find_rar_creator() -> str | None:
    from backend.core.config import get_settings

    settings = get_settings()
    candidates: list[Path] = []
    if settings.comic_rar_tool_path:
        candidates.append(Path(settings.comic_rar_tool_path).expanduser())
    if settings.comic_rar_tools_dir:
        tools_dir = Path(settings.comic_rar_tools_dir).expanduser()
        candidates.extend([tools_dir / "rar.exe", tools_dir / "rar"])

    for candidate in candidates:
        if candidate.exists() and candidate.name.lower().startswith("rar"):
            return str(candidate)

    for name in ("rar", "rar.exe"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def _create_cbr_archive(source_dir: str, target_path: str) -> int:
    rar_creator = _find_rar_creator()
    if not rar_creator:
        raise ValueError(
            "CBR conversion requires a RAR CLI capable of writing archives. "
            "Configure COMIC_RAR_TOOL_PATH with the rar executable."
        )

    relative_files = [
        path.relative_to(source_dir).as_posix()
        for path in sorted(Path(source_dir).rglob("*"))
        if path.is_file()
    ]
    if not relative_files:
        raise ValueError("No files available to package as CBR")

    process = subprocess.run(
        [rar_creator, "a", "-idq", target_path, *relative_files],
        cwd=source_dir,
        capture_output=True,
        check=False,
        env=_rar_cli_subprocess_env(),
    )
    if process.returncode != 0:
        stderr = process.stderr.decode("utf-8", errors="ignore").strip()
        stdout = process.stdout.decode("utf-8", errors="ignore").strip()
        message = stderr or stdout or f"RAR exited with code {process.returncode}"
        raise ValueError(f"Failed to create CBR archive: {message[:500]}")
    return len(relative_files)


def _is_passthrough_conversion(source_format: str, target_format: str) -> bool:
    return (
        source_format in ZIP_LIKE_EXTENSIONS
        and target_format == "cbz"
    ) or (
        source_format in RAR_LIKE_EXTENSIONS
        and target_format == "cbr"
    )


class ComicArchiveConversionService:
    """Convert indexed comic archives and upload the results beside the source files."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.transfer_service = DriveTransferService()

    async def convert_indexed_items(
        self,
        *,
        account_id: UUID,
        indexed_items: list[IndexedArchiveItem],
        source_format: str,
        target_format: str,
        delete_source_after_convert: bool = False,
        progress_reporter=None,
    ) -> dict[str, Any]:
        source_format, target_format = validate_archive_conversion(
            source_format, target_format
        )
        account = await self.session.get(LinkedAccount, account_id)
        if account is None:
            raise ValueError(f"Linked account {account_id} not found")

        client = build_drive_client(account, TokenManager(self.session))
        stats: dict[str, Any] = {
            "total": len(indexed_items),
            "converted": 0,
            "skipped": 0,
            "failed": 0,
            "deleted_source": 0,
            "source_format": source_format,
            "target_format": target_format,
            "error_items": [],
            "error_items_truncated": 0,
        }
        error_items = ErrorItemsCollector(stats, limit=CONVERSION_ERROR_ITEMS_LIMIT)

        for item in indexed_items:
            try:
                if item.item_type != "file":
                    stats["skipped"] += 1
                    continue
                item_ext = str(item.extension or "").strip().lower()
                if item_ext not in source_extensions_for_format(source_format):
                    stats["skipped"] += 1
                    continue
                await self._convert_single_item(
                    client=client,
                    account=account,
                    item=item,
                    source_format=source_format,
                    target_format=target_format,
                    delete_source_after_convert=delete_source_after_convert,
                )
                stats["converted"] += 1
                if delete_source_after_convert:
                    stats["deleted_source"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["failed"] += 1
                error_items.record(
                    reason=str(exc).strip() or exc.__class__.__name__,
                    item_id=item.id,
                    item_name=item.name,
                    account_id=str(account_id),
                    stage="convert_archive",
                )
            finally:
                if progress_reporter is not None:
                    await progress_reporter.increment()
                    if progress_reporter.current % 5 == 0:
                        await progress_reporter.update_metrics(
                            converted=stats["converted"],
                            skipped=stats["skipped"],
                            failed=stats["failed"],
                            deleted_source=stats["deleted_source"],
                            source_format=source_format,
                            target_format=target_format,
                            error_items=stats.get("error_items", []),
                            error_items_truncated=stats.get("error_items_truncated", 0),
                        )

        return stats

    async def _convert_single_item(
        self,
        *,
        client,
        account: LinkedAccount,
        item: IndexedArchiveItem,
        source_format: str,
        target_format: str,
        delete_source_after_convert: bool = False,
    ) -> None:
        target_name = f"{Path(item.name).stem}.{target_format}"
        parent_folder_id = str(item.parent_id or "root").strip() or "root"
        parent_path = _parent_path(item.path)

        with tempfile.TemporaryDirectory(prefix="comic_convert_") as temp_dir:
            source_path = str(Path(temp_dir) / item.name)
            await client.download_file_to_path(account, item.id, source_path)

            if _is_passthrough_conversion(source_format, target_format):
                archive_path = source_path
            else:
                extract_dir = str(Path(temp_dir) / "extract")
                Path(extract_dir).mkdir(parents=True, exist_ok=True)
                if source_format in ZIP_LIKE_EXTENSIONS:
                    _extract_zip_archive(source_path, extract_dir)
                elif source_format in RAR_LIKE_EXTENSIONS:
                    _extract_rar_archive(source_path, extract_dir)
                else:
                    raise ValueError(f"Unsupported archive source format: {source_format}")

                archive_path = str(Path(temp_dir) / target_name)
                if target_format == "cbz":
                    _create_cbz_archive(extract_dir, archive_path)
                elif target_format == "cbr":
                    _create_cbr_archive(extract_dir, archive_path)
                else:
                    raise ValueError(f"Unsupported archive target format: {target_format}")

            uploaded_item_id = await self.transfer_service.upload_local_file(
                client=client,
                account=account,
                local_path=archive_path,
                filename=target_name,
                folder_id=parent_folder_id,
                conflict_behavior="rename",
                force_resumable=True,
            )
            if not uploaded_item_id:
                raise RuntimeError("Archive conversion upload did not return item id")

            uploaded_item = await client.get_item_metadata(account, uploaded_item_id)
            await upsert_item_record(
                self.session,
                account_id=account.id,
                item_data=uploaded_item,
                parent_id=None if parent_folder_id == "root" else parent_folder_id,
                path=build_item_path(parent_path, uploaded_item.name),
            )

            if delete_source_after_convert:
                await client.delete_item(account, item.id)
                await delete_item_and_descendants(
                    self.session,
                    account_id=account.id,
                    item_id=item.id,
                )
