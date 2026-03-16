"""ZIP extraction workflow for drive-backed accounts."""

from __future__ import annotations

import logging
import posixpath
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.drive.transfer_service import DriveTransferService
from backend.common.error_items import ErrorItemsCollector
from backend.services.auto_metadata_mapper import (
    AutoMapCandidate,
    enqueue_auto_mapping_jobs,
)
from backend.services.item_index import (
    build_item_path,
    delete_item_and_descendants,
    path_from_breadcrumb,
    upsert_item_record,
)
from backend.db.models import LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.workers.job_progress import JobProgressReporter

logger = logging.getLogger(__name__)
ZIP_ERROR_ITEMS_LIMIT = 50
COPY_CHUNK_SIZE = 64 * 1024


@dataclass(slots=True)
class _FolderState:
    folder_id: str
    path: str
    name: str
    parent_id: str | None
    size: int = 0
    mime_type: str | None = None
    created_at: Any = None
    modified_at: Any = None


class ZipExtractionService:
    """Extract one source ZIP into a destination account/folder."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.transfer_service = DriveTransferService()

    async def extract_zip(
        self,
        *,
        source_account_id: UUID,
        source_item_id: str,
        destination_account_id: UUID,
        destination_folder_id: str = "root",
        delete_source_after_extract: bool = False,
        progress_reporter: JobProgressReporter | None = None,
    ) -> dict[str, Any]:
        source_account = await self.session.get(LinkedAccount, source_account_id)
        destination_account = await self.session.get(LinkedAccount, destination_account_id)
        if not source_account or not destination_account:
            raise ValueError("Source or destination account not found")

        token_manager = TokenManager(self.session)
        source_client = build_drive_client(source_account, token_manager)
        destination_client = build_drive_client(destination_account, token_manager)

        source_item = await source_client.get_item_metadata(source_account, source_item_id)
        if (source_item.item_type or "").lower() != "file":
            raise ValueError("ZIP extraction supports files only")

        extension = Path(source_item.name or "").suffix.lower()
        if extension != ".zip":
            raise ValueError("ZIP extraction supports only .zip files")

        wrapper_name = _wrapper_folder_name(source_item.name, source_item_id)
        destination_root_path = await _destination_root_path(
            client=destination_client,
            account=destination_account,
            folder_id=destination_folder_id,
        )

        with tempfile.TemporaryDirectory(prefix="zip_extract_") as temp_dir:
            source_filename = Path(str(source_item.name or "")).name or f"{source_item_id}.zip"
            download_path = str(Path(temp_dir) / source_filename)
            await source_client.download_file_to_path(source_account, source_item_id, download_path)

            with zipfile.ZipFile(download_path, "r") as archive:
                entries = _prepare_entries(archive)
                _strip_common_root_directory(entries)
                if not entries:
                    raise ValueError("ZIP has no extractable regular files")
                if not any(entry["skip_reason"] is None for entry in entries):
                    raise ValueError("ZIP has no extractable regular files")

                stats: dict[str, Any] = {
                    "total": len(entries),
                    "success": 0,
                    "failed": 0,
                    "skipped": 0,
                    "created_folders": 0,
                    "wrapper_folder_id": None,
                    "wrapper_folder_name": None,
                    "deleted_source": False,
                    "auto_jobs_created": 0,
                    "auto_job_ids": [],
                    "error_items": [],
                    "error_items_truncated": 0,
                }
                error_items = ErrorItemsCollector(stats, limit=ZIP_ERROR_ITEMS_LIMIT)
                if progress_reporter is not None:
                    await progress_reporter.set_total(stats["total"])
                    _sync_progress_metrics(progress_reporter, stats)

                wrapper_folder = await destination_client.create_folder(
                    destination_account,
                    wrapper_name,
                    destination_folder_id,
                    conflict_behavior="rename",
                )
                wrapper_parent_id = None if destination_folder_id == "root" else destination_folder_id
                wrapper_path = build_item_path(destination_root_path, wrapper_folder.name)
                await upsert_item_record(
                    self.session,
                    account_id=destination_account.id,
                    item_data=wrapper_folder,
                    parent_id=wrapper_parent_id,
                    path=wrapper_path,
                )
                stats["created_folders"] = 1
                stats["wrapper_folder_id"] = wrapper_folder.id
                stats["wrapper_folder_name"] = wrapper_folder.name

                wrapper_state = _FolderState(
                    folder_id=wrapper_folder.id,
                    path=wrapper_path,
                    name=wrapper_folder.name,
                    parent_id=wrapper_parent_id,
                    mime_type=wrapper_folder.mime_type,
                    created_at=wrapper_folder.created_at,
                    modified_at=wrapper_folder.modified_at,
                )
                folder_cache: dict[str, _FolderState] = {
                    "": wrapper_state,
                }
                auto_candidates: list[AutoMapCandidate] = []

                for entry in entries:
                    info = entry["info"]
                    member_name = str(info.filename or "")
                    skip_reason = entry["skip_reason"]
                    normalized_parts = entry["parts"]

                    if skip_reason or not normalized_parts:
                        stats["skipped"] += 1
                        error_items.record(
                            reason=skip_reason or "ZIP member could not be extracted",
                            item_id=source_item_id,
                            item_name=member_name,
                            account_id=str(source_account.id),
                            stage="extract_zip_member",
                        )
                        if progress_reporter is not None:
                            _sync_progress_metrics(progress_reporter, stats)
                            await progress_reporter.increment()
                        continue

                    relative_dirs = normalized_parts[:-1]
                    filename = normalized_parts[-1]
                    temp_member_path: str | None = None
                    try:
                        target_folder = await self._ensure_destination_folder(
                            relative_dirs=relative_dirs,
                            folder_cache=folder_cache,
                            account=destination_account,
                            client=destination_client,
                            wrapper_folder=folder_cache[""],
                            stats=stats,
                        )
                        temp_member_path = _extract_member_to_temp(
                            archive=archive,
                            info=info,
                            temp_dir=temp_dir,
                        )
                        uploaded_item_id = await self.transfer_service.upload_local_file(
                            client=destination_client,
                            account=destination_account,
                            local_path=temp_member_path,
                            filename=filename,
                            folder_id=target_folder.folder_id,
                            conflict_behavior="rename",
                            force_resumable=True,
                        )
                        if not uploaded_item_id:
                            raise ValueError("Destination provider did not return uploaded item id")

                        uploaded_item = await destination_client.get_item_metadata(
                            destination_account,
                            uploaded_item_id,
                        )
                        uploaded_path = build_item_path(target_folder.path, uploaded_item.name)
                        await upsert_item_record(
                            self.session,
                            account_id=destination_account.id,
                            item_data=uploaded_item,
                            parent_id=target_folder.folder_id,
                            path=uploaded_path,
                        )
                        _accumulate_folder_sizes(
                            folder_cache=folder_cache,
                            relative_dirs=relative_dirs,
                            size=int(uploaded_item.size or 0),
                        )
                        auto_candidates.append(
                            AutoMapCandidate(
                                item_id=str(uploaded_item.id),
                                name=uploaded_item.name,
                                extension=Path(uploaded_item.name).suffix.lstrip(".").lower(),
                                item_type=uploaded_item.item_type,
                            )
                        )
                        stats["success"] += 1
                    except Exception as exc:  # noqa: BLE001
                        stats["failed"] += 1
                        error_items.record(
                            reason=str(exc).strip() or exc.__class__.__name__,
                            item_id=source_item_id,
                            item_name=member_name,
                            account_id=str(source_account.id),
                            stage="extract_zip_member",
                        )
                    finally:
                        if temp_member_path:
                            try:
                                Path(temp_member_path).unlink(missing_ok=True)
                            except Exception:
                                logger.warning("Failed to cleanup temp ZIP member: %s", temp_member_path)
                        if progress_reporter is not None:
                            _sync_progress_metrics(progress_reporter, stats)
                            await progress_reporter.increment()

                await self._persist_folder_sizes(
                    account_id=destination_account.id,
                    folder_cache=folder_cache,
                )

                if auto_candidates:
                    auto_summary = await enqueue_auto_mapping_jobs(
                        self.session,
                        account_id=destination_account.id,
                        candidates=auto_candidates,
                        source="extract_zip_contents",
                        chunk_size=100,
                    )
                    stats["auto_jobs_created"] = int(auto_summary.get("total_jobs", 0))
                    stats["auto_job_ids"] = auto_summary.get("job_ids", [])

                if delete_source_after_extract and stats["failed"] == 0 and stats["success"] > 0:
                    await source_client.delete_item(source_account, source_item_id)
                    await delete_item_and_descendants(
                        self.session,
                        account_id=source_account.id,
                        item_id=source_item_id,
                    )
                    stats["deleted_source"] = True

                if progress_reporter is not None:
                    _sync_progress_metrics(progress_reporter, stats)
                    await progress_reporter.flush(force=True)

                return stats

    async def _ensure_destination_folder(
        self,
        *,
        relative_dirs: list[str],
        folder_cache: dict[str, _FolderState],
        account: LinkedAccount,
        client: DriveProviderClient,
        wrapper_folder: _FolderState,
        stats: dict[str, Any],
    ) -> _FolderState:
        if not relative_dirs:
            return wrapper_folder

        current_state = wrapper_folder
        relative_key = ""
        for part in relative_dirs:
            relative_key = f"{relative_key}/{part}" if relative_key else part
            cached = folder_cache.get(relative_key)
            if cached:
                current_state = cached
                continue

            created = await client.create_folder(
                account,
                part,
                current_state.folder_id,
                conflict_behavior="rename",
            )
            created_path = build_item_path(current_state.path, created.name)
            await upsert_item_record(
                self.session,
                account_id=account.id,
                item_data=created,
                parent_id=current_state.folder_id,
                path=created_path,
            )
            parent_folder_id = current_state.folder_id
            current_state = _FolderState(
                folder_id=created.id,
                path=created_path,
                name=created.name,
                parent_id=parent_folder_id,
                mime_type=created.mime_type,
                created_at=created.created_at,
                modified_at=created.modified_at,
            )
            folder_cache[relative_key] = current_state
            stats["created_folders"] = int(stats.get("created_folders", 0) or 0) + 1
        return current_state

    async def _persist_folder_sizes(
        self,
        *,
        account_id: UUID,
        folder_cache: dict[str, _FolderState],
    ) -> None:
        for folder_state in sorted(
            folder_cache.values(),
            key=lambda candidate: (candidate.path.count("/"), candidate.path),
        ):
            await upsert_item_record(
                self.session,
                account_id=account_id,
                item_data=_folder_item_data(folder_state),
                parent_id=folder_state.parent_id,
                path=folder_state.path,
            )


def _wrapper_folder_name(source_name: str | None, source_item_id: str) -> str:
    wrapper_name = Path(source_name or "").stem.strip()
    if wrapper_name:
        return wrapper_name
    fallback = Path(source_name or "").name.strip()
    return fallback or f"extract-{source_item_id}"


async def _destination_root_path(
    *,
    client: DriveProviderClient,
    account: LinkedAccount,
    folder_id: str,
) -> str:
    if folder_id == "root":
        return "/"
    breadcrumb = await client.get_item_path(account, folder_id)
    path = path_from_breadcrumb(breadcrumb)
    return path or "/"


def _prepare_entries(archive: zipfile.ZipFile) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        if info.flag_bits & 0x1:
            raise ValueError("Password-protected ZIPs are not supported")
        parts, reason = _normalize_member_path(info.filename)
        if reason is None and _is_symlink_entry(info):
            reason = "Symlink ZIP entries are not supported"
        entries.append({
            "info": info,
            "parts": parts,
            "skip_reason": reason,
        })
    return entries


def _strip_common_root_directory(entries: list[dict[str, Any]]) -> None:
    extractable_entries = [
        entry
        for entry in entries
        if entry["skip_reason"] is None and entry["parts"]
    ]
    if not extractable_entries:
        return

    if any(len(entry["parts"]) < 2 for entry in extractable_entries):
        return

    top_level_parts = {entry["parts"][0] for entry in extractable_entries}
    if len(top_level_parts) != 1:
        return

    for entry in extractable_entries:
        entry["parts"] = entry["parts"][1:]


def _normalize_member_path(raw_name: str | None) -> tuple[list[str] | None, str | None]:
    normalized = posixpath.normpath(str(raw_name or "").replace("\\", "/"))
    if normalized in {"", ".", "/"}:
        return None, "ZIP entry has an empty path"
    if normalized.startswith("/") or normalized == ".." or normalized.startswith("../"):
        return None, "ZIP entry path is not safe for extraction"

    parts: list[str] = []
    for raw_part in normalized.split("/"):
        part = str(raw_part or "").strip()
        if not part or part == ".":
            continue
        if part == "..":
            return None, "ZIP entry path is not safe for extraction"
        if any(marker in part for marker in ("/", "\\", "\x00")):
            return None, "ZIP entry path is not safe for extraction"
        safe_name = Path(part).name.strip()
        if not safe_name or safe_name in {".", ".."}:
            return None, "ZIP entry path is not safe for extraction"
        parts.append(safe_name)

    if not parts:
        return None, "ZIP entry has an empty path"
    return parts, None


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    mode = (int(info.external_attr) >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _extract_member_to_temp(
    *,
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    temp_dir: str,
) -> str:
    suffix = Path(str(info.filename or "")).suffix
    with tempfile.NamedTemporaryFile(
        prefix="zip_member_",
        suffix=suffix,
        dir=temp_dir,
        delete=False,
    ) as handle:
        with archive.open(info, "r") as source:
            shutil.copyfileobj(source, handle, length=COPY_CHUNK_SIZE)
        return handle.name


def _accumulate_folder_sizes(
    *,
    folder_cache: dict[str, _FolderState],
    relative_dirs: list[str],
    size: int,
) -> None:
    if size <= 0:
        return

    root_folder = folder_cache.get("")
    if root_folder is not None:
        root_folder.size += size

    relative_key = ""
    for part in relative_dirs:
        relative_key = f"{relative_key}/{part}" if relative_key else part
        folder_state = folder_cache.get(relative_key)
        if folder_state is not None:
            folder_state.size += size


def _folder_item_data(folder_state: _FolderState) -> SimpleNamespace:
    return SimpleNamespace(
        id=folder_state.folder_id,
        name=folder_state.name,
        item_type="folder",
        size=folder_state.size,
        mime_type=folder_state.mime_type,
        created_at=folder_state.created_at,
        modified_at=folder_state.modified_at,
    )


def _sync_progress_metrics(progress: JobProgressReporter, stats: dict[str, Any]) -> None:
    progress.metrics.update(
        total=int(stats.get("total", 0) or 0),
        success=int(stats.get("success", 0) or 0),
        failed=int(stats.get("failed", 0) or 0),
        skipped=int(stats.get("skipped", 0) or 0),
        created_folders=int(stats.get("created_folders", 0) or 0),
        wrapper_folder_id=stats.get("wrapper_folder_id"),
        wrapper_folder_name=stats.get("wrapper_folder_name"),
        deleted_source=bool(stats.get("deleted_source")),
        auto_jobs_created=int(stats.get("auto_jobs_created", 0) or 0),
        auto_job_ids=list(stats.get("auto_job_ids") or []),
        error_items=list(stats.get("error_items") or []),
        error_items_truncated=int(stats.get("error_items_truncated", 0) or 0),
    )
