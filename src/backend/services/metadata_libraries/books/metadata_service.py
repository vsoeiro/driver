"""Book extraction and metadata mapping helpers."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.error_items import ErrorItemsCollector
from backend.db.models import ItemMetadata, LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.metadata_libraries.comics.metadata_service import (
    ComicExtractionResult,
    extract_comic_asset,
    file_extension,
    optimize_cover_image,
)
from backend.services.metadata_libraries.service import MetadataLibraryService
from backend.services.metadata_libraries.settings import (
    CoverRuntimeSettings,
    MetadataLibrarySettingsService,
)
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client

BOOK_MAPPING_COMMIT_BATCH_SIZE = 10
BOOK_ERROR_ITEMS_LIMIT = 50
SUPPORTED_BOOK_EXTENSIONS = {"pdf", "epub"}


@dataclass(slots=True)
class IndexedBookItem:
    id: str
    name: str
    extension: str | None = None
    item_type: str = "file"
    size: int | None = None


class BookMetadataService:
    """Service for extracting and mapping book metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _init_stats(total: int) -> dict[str, Any]:
        return {
            "total": total,
            "mapped": 0,
            "skipped": 0,
            "failed": 0,
            "error_items": [],
            "error_items_truncated": 0,
        }

    async def process_item_ids(
        self,
        account_id: UUID,
        item_ids: list[str],
        *,
        job_id: UUID | None = None,
        batch_id: UUID | None = None,
        progress_reporter=None,
        initialize_progress_total: bool = True,
    ) -> dict[str, Any]:
        account = await self.session.get(LinkedAccount, account_id)
        if not account:
            raise ValueError("Account not found")

        token_manager = TokenManager(self.session)
        source_client = build_drive_client(account, token_manager)
        files_to_process = await self._expand_items(source_client, account, item_ids)
        return await self._process(
            account=account,
            source_client=source_client,
            files_to_process=files_to_process,
            job_id=job_id,
            batch_id=batch_id,
            progress_reporter=progress_reporter,
            initialize_progress_total=initialize_progress_total,
        )

    async def process_indexed_items(
        self,
        account_id: UUID,
        files_to_process: list[Any],
        *,
        job_id: UUID | None = None,
        batch_id: UUID | None = None,
        progress_reporter=None,
        initialize_progress_total: bool = True,
    ) -> dict[str, Any]:
        account = await self.session.get(LinkedAccount, account_id)
        if not account:
            raise ValueError("Account not found")

        token_manager = TokenManager(self.session)
        source_client = build_drive_client(account, token_manager)
        return await self._process(
            account=account,
            source_client=source_client,
            files_to_process=files_to_process,
            job_id=job_id,
            batch_id=batch_id,
            progress_reporter=progress_reporter,
            initialize_progress_total=initialize_progress_total,
        )

    async def _process(
        self,
        *,
        account: LinkedAccount,
        source_client: DriveProviderClient,
        files_to_process: list[Any],
        job_id: UUID | None,
        batch_id: UUID | None,
        progress_reporter,
        initialize_progress_total: bool,
    ) -> dict[str, Any]:
        library_service = MetadataLibraryService(self.session)
        category = await library_service.ensure_active_books_category()
        attr_ids = await library_service.books_attribute_id_map()
        cover_settings = await MetadataLibrarySettingsService(
            self.session
        ).get_books_runtime_settings()

        token_manager = TokenManager(self.session)
        target_account = account
        if cover_settings.storage_account_id:
            maybe_target = await self.session.get(
                LinkedAccount, UUID(str(cover_settings.storage_account_id))
            )
            if maybe_target:
                target_account = maybe_target
        cover_client = build_drive_client(target_account, token_manager)
        cover_folder_id = await self._ensure_cover_folder(
            cover_client,
            target_account,
            parent_folder_id=cover_settings.storage_parent_folder_id,
            cover_folder_name=cover_settings.storage_folder_name,
        )

        stats = self._init_stats(len(files_to_process))
        error_collector = ErrorItemsCollector(stats, limit=BOOK_ERROR_ITEMS_LIMIT)
        if progress_reporter is not None and initialize_progress_total:
            await progress_reporter.set_total(stats["total"])

        processed_since_commit = 0
        for file_item in files_to_process:
            item_id = str(getattr(file_item, "id", ""))
            item_name = str(getattr(file_item, "name", item_id))
            try:
                mapped = await self._process_single_file(
                    source_client=source_client,
                    source_account=account,
                    cover_client=cover_client,
                    cover_account=target_account,
                    item=file_item,
                    cover_folder_id=cover_folder_id,
                    category_id=category.id,
                    attr_ids=attr_ids,
                    cover_settings=cover_settings,
                    job_id=job_id,
                    batch_id=batch_id,
                )
                if mapped:
                    stats["mapped"] += 1
                else:
                    stats["skipped"] += 1

                processed_since_commit += 1
                if processed_since_commit >= BOOK_MAPPING_COMMIT_BATCH_SIZE:
                    await self.session.commit()
                    processed_since_commit = 0
            except Exception as exc:
                await self.session.rollback()
                stats["failed"] += 1
                error_collector.record(
                    reason=str(exc),
                    item_id=item_id,
                    item_name=item_name,
                    stage="map_book",
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
        return stats

    async def _process_single_file(
        self,
        *,
        source_client: DriveProviderClient,
        source_account: LinkedAccount,
        cover_client: DriveProviderClient,
        cover_account: LinkedAccount,
        item: Any,
        cover_folder_id: str,
        category_id: UUID,
        attr_ids: dict[str, str],
        cover_settings: CoverRuntimeSettings,
        job_id: UUID | None,
        batch_id: UUID | None,
    ) -> bool:
        ext = (getattr(item, "extension", None) or file_extension(item.name)).lower()
        if ext not in SUPPORTED_BOOK_EXTENSIONS:
            return False

        if await self._is_conflicting_or_already_mapped(
            account_id=source_account.id,
            item_id=item.id,
            category_id=category_id,
            attr_ids=attr_ids,
        ):
            return False

        temp_dir = tempfile.mkdtemp(prefix="book_extract_")
        local_path = str(Path(temp_dir) / f"{item.id}.{ext or 'bin'}")
        try:
            await source_client.download_file_to_path(
                source_account,
                item.id,
                local_path,
            )
            extraction = extract_comic_asset(local_path, ext)
            mapped_values = self._build_metadata_values(
                item=item,
                extraction=extraction,
                attr_ids=attr_ids,
            )

            if extraction.cover_bytes:
                optimized_cover, cover_ext, _ = optimize_cover_image(
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

            await apply_metadata_change(
                self.session,
                account_id=source_account.id,
                item_id=item.id,
                category_id=category_id,
                values=mapped_values,
                batch_id=batch_id,
                job_id=job_id,
            )
            return True
        except ValueError as exc:
            # Invalid/unsupported file content should be skipped, not failed.
            error_text = str(exc).lower()
            if "no cover image" in error_text or "no image pages" in error_text:
                return False
            raise
        finally:
            try:
                Path(local_path).unlink(missing_ok=True)
                Path(temp_dir).rmdir()
            except Exception:
                pass

    @staticmethod
    def _build_metadata_values(
        *,
        item: Any,
        extraction: ComicExtractionResult,
        attr_ids: dict[str, str],
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}

        def set_if_exists(field_key: str, value: Any) -> None:
            attr_id = attr_ids.get(field_key)
            if attr_id and value is not None:
                values[attr_id] = value

        set_if_exists("title", Path(str(getattr(item, "name", ""))).stem or None)
        set_if_exists("file_format", extraction.format)
        set_if_exists("page_count", extraction.page_count)
        return values

    async def _is_conflicting_or_already_mapped(
        self, *, account_id: UUID, item_id: str, category_id: UUID, attr_ids: dict[str, str]
    ) -> bool:
        stmt = select(ItemMetadata).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.item_id == item_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            return False
        if existing.category_id != category_id:
            return True

        values = existing.values or {}
        for field_key in (
            "cover_item_id",
            "cover_account_id",
            "cover_filename",
            "page_count",
            "file_format",
        ):
            attr_id = attr_ids.get(field_key)
            if not attr_id:
                continue
            value = values.get(attr_id)
            if value is not None and value != "":
                return True
        return False

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
