"""Book extraction and metadata mapping helpers."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.drive.transfer_service import DriveTransferService
from backend.common.error_items import ErrorItemsCollector
from backend.core.exceptions import DriveOrganizerError
from backend.db.models import ItemMetadata, LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.item_index import parent_id_from_breadcrumb
from backend.services.metadata_libraries.implementations.books.schema import (
    BOOKS_LIBRARY_KEY,
)
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
        force_remap: bool = False,
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
            force_remap=force_remap,
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
        force_remap: bool,
    ) -> dict[str, Any]:
        library_service = MetadataLibraryService(self.session)
        category = await library_service.require_active_books_category()
        attr_ids = await library_service.books_attribute_id_map(ensure_schema=False)
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
        cover_folder_id = await self._resolve_cover_folder_id(
            client=cover_client,
            account=target_account,
            cover_settings=cover_settings,
        )
        existing_metadata_by_item_id = await self._load_existing_metadata_values(
            account_id=account.id,
            item_ids=[
                str(getattr(file_item, "id", ""))
                for file_item in files_to_process
                if str(getattr(file_item, "id", "")).strip()
            ],
            category_id=category.id,
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
                    force_remap=force_remap,
                    existing_metadata_values=existing_metadata_by_item_id.get(
                        str(getattr(file_item, "id", ""))
                    ),
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
        force_remap: bool,
        existing_metadata_values: dict[str, Any] | None = None,
    ) -> bool:
        ext = (getattr(item, "extension", None) or file_extension(item.name)).lower()
        if ext not in SUPPORTED_BOOK_EXTENSIONS:
            return False

        if not force_remap:
            if await self._is_conflicting_or_already_mapped(
                account_id=source_account.id,
                item_id=item.id,
                category_id=category_id,
                attr_ids=attr_ids,
            ):
                return False
        else:
            relocated = await self._maybe_reuse_or_move_existing_cover(
                source_account=source_account,
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
            if relocated is not None:
                return relocated

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

            mapped_values = self._merge_library_mapped_values(
                existing_metadata_values=existing_metadata_values,
                mapped_values=mapped_values,
                attr_ids=attr_ids,
            )

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

    async def reindex_mapped_books(
        self, *, job_id: UUID | None = None, batch_id: UUID | None = None
    ) -> dict[str, Any]:
        library_service = MetadataLibraryService(self.session)
        category = await library_service.require_active_books_category()
        stmt = select(ItemMetadata.account_id, ItemMetadata.item_id).where(
            ItemMetadata.category_id == category.id
        )
        rows = (await self.session.execute(stmt)).all()
        by_account: dict[UUID, list[str]] = {}
        for account_id, item_id in rows:
            by_account.setdefault(account_id, []).append(str(item_id))
        if not by_account:
            return self._init_stats(0)

        overall = self._init_stats(sum(len(item_ids) for item_ids in by_account.values()))
        for account_id, item_ids in by_account.items():
            account = await self.session.get(LinkedAccount, account_id)
            if account is None:
                overall["failed"] += len(item_ids)
                continue
            token_manager = TokenManager(self.session)
            source_client = build_drive_client(account, token_manager)
            files_to_process = await self._expand_items(source_client, account, item_ids)
            account_stats = await self._process(
                account=account,
                source_client=source_client,
                files_to_process=files_to_process,
                job_id=job_id,
                batch_id=batch_id,
                progress_reporter=None,
                initialize_progress_total=False,
                force_remap=True,
            )
            overall["mapped"] += account_stats["mapped"]
            overall["skipped"] += account_stats["skipped"]
            overall["failed"] += account_stats["failed"]
            overall["error_items"].extend(account_stats.get("error_items", []))
            overall["error_items_truncated"] += account_stats.get("error_items_truncated", 0)
        return overall

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

    @staticmethod
    def _merge_library_mapped_values(
        *,
        existing_metadata_values: dict[str, Any] | None,
        mapped_values: dict[str, Any],
        attr_ids: dict[str, str],
    ) -> dict[str, Any]:
        if not existing_metadata_values:
            return mapped_values

        merged_values = dict(existing_metadata_values)

        for field_key in (
            "file_format",
            "page_count",
            "cover_item_id",
            "cover_account_id",
            "cover_filename",
        ):
            attr_id = attr_ids.get(field_key)
            if attr_id and attr_id in mapped_values:
                merged_values[attr_id] = mapped_values[attr_id]

        title_attr = attr_ids.get("title")
        if title_attr and title_attr in mapped_values and title_attr not in merged_values:
            merged_values[title_attr] = mapped_values[title_attr]

        return merged_values

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
        cover_settings: CoverRuntimeSettings,
    ) -> str:
        configured_folder_id = str(
            getattr(cover_settings, "storage_folder_id", None) or ""
        ).strip()
        is_persistable_target = (
            getattr(cover_settings, "storage_account_id", None) is not None
            and str(account.id) == str(getattr(cover_settings, "storage_account_id"))
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
                    and item.name == cover_settings.storage_folder_name
                ):
                    return item.id

        cover_folder_id = await self._ensure_cover_folder(
            client,
            account,
            parent_folder_id=cover_settings.storage_parent_folder_id,
            cover_folder_name=cover_settings.storage_folder_name,
        )
        if is_persistable_target:
            await MetadataLibrarySettingsService(
                self.session
            ).persist_cover_storage_folder_id(
                BOOKS_LIBRARY_KEY,
                folder_id=cover_folder_id,
            )
        return cover_folder_id

    async def _load_existing_metadata_values(
        self,
        *,
        account_id: UUID,
        item_ids: list[str],
        category_id: UUID,
    ) -> dict[str, dict[str, Any]]:
        if not item_ids:
            return {}
        stmt = select(ItemMetadata.item_id, ItemMetadata.values).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.category_id == category_id,
            ItemMetadata.item_id.in_(item_ids),
        )
        rows = (await self.session.execute(stmt)).all()
        return {
            str(item_id): dict(values or {})
            for item_id, values in rows
            if str(item_id).strip()
        }

    async def _maybe_reuse_or_move_existing_cover(
        self,
        *,
        source_account: LinkedAccount,
        item_id: str,
        cover_client: DriveProviderClient,
        cover_account: LinkedAccount,
        cover_folder_id: str,
        attr_ids: dict[str, str],
        existing_metadata_values: dict[str, Any] | None,
        category_id: UUID,
        job_id: UUID | None,
        batch_id: UUID | None,
    ) -> bool | None:
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
            existing_cover_account_uuid = UUID(existing_cover_account_id)
        except ValueError:
            return None
        existing_cover_account = await self.session.get(
            LinkedAccount, existing_cover_account_uuid
        )
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
                return False

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
            account_id=source_account.id,
            item_id=item_id,
            category_id=category_id,
            values=moved_values,
            batch_id=batch_id,
            job_id=job_id,
        )
        return True
