"""Image analysis orchestration + metadata persistence."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.error_items import ErrorItemsCollector
from backend.core.config import get_settings
from backend.db.models import ImageAnalysisResult as ImageAnalysisResultRow
from backend.db.models import LinkedAccount
from backend.db.models import ItemMetadata
from backend.security.token_manager import TokenManager
from backend.services.image_analysis import (
    SUPPORTED_IMAGE_EXTENSIONS,
    ImageAnalysisError,
    UnsupportedImageError,
)
from backend.services.image_analysis.pipeline import ImageAnalysisPipeline
from backend.services.metadata_libraries.service import MetadataLibraryService
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client

IMAGE_ERROR_ITEMS_LIMIT = 50


@dataclass(slots=True)
class IndexedImageItem:
    id: str
    name: str
    extension: str | None = None
    item_type: str = "file"
    size: int | None = None


def _file_extension(filename: str | None) -> str:
    if not filename:
        return ""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


class ImageAnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.pipeline = ImageAnalysisPipeline()

    def _init_stats(self, total: int) -> dict[str, Any]:
        return {
            "total": total,
            "processed": 0,
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
        reprocess: bool = False,
    ) -> dict[str, Any]:
        account = await self.session.get(LinkedAccount, account_id)
        if not account:
            raise ValueError("Account not found")

        library_service = MetadataLibraryService(self.session)
        category = await library_service.ensure_active_images_category()
        attr_ids = await library_service.images_attribute_id_map()

        token_manager = TokenManager(self.session)
        client = build_drive_client(account, token_manager)
        files = await self._expand_items(client, account, item_ids)
        stats = self._init_stats(len(files))
        if progress_reporter is not None:
            await progress_reporter.set_total(stats["total"])

        return await self._process_files(
            account=account,
            client=client,
            files=files,
            category_id=category.id,
            attr_ids=attr_ids,
            stats=stats,
            job_id=job_id,
            batch_id=batch_id,
            progress_reporter=progress_reporter,
            reprocess=reprocess,
        )

    async def process_indexed_items(
        self,
        account_id: UUID,
        files: list[IndexedImageItem],
        *,
        job_id: UUID | None = None,
        batch_id: UUID | None = None,
        progress_reporter=None,
        reprocess: bool = False,
        initialize_progress_total: bool = True,
    ) -> dict[str, Any]:
        account = await self.session.get(LinkedAccount, account_id)
        if not account:
            raise ValueError("Account not found")

        library_service = MetadataLibraryService(self.session)
        category = await library_service.ensure_active_images_category()
        attr_ids = await library_service.images_attribute_id_map()

        token_manager = TokenManager(self.session)
        client = build_drive_client(account, token_manager)
        stats = self._init_stats(len(files))
        if progress_reporter is not None and initialize_progress_total:
            await progress_reporter.set_total(stats["total"])

        return await self._process_files(
            account=account,
            client=client,
            files=files,
            category_id=category.id,
            attr_ids=attr_ids,
            stats=stats,
            job_id=job_id,
            batch_id=batch_id,
            progress_reporter=progress_reporter,
            reprocess=reprocess,
        )

    async def _process_files(
        self,
        *,
        account: LinkedAccount,
        client: DriveProviderClient,
        files: list[Any],
        category_id,
        attr_ids: dict[str, str],
        stats: dict[str, Any],
        job_id,
        batch_id,
        progress_reporter,
        reprocess: bool,
    ) -> dict[str, Any]:
        error_collector = ErrorItemsCollector(stats, limit=IMAGE_ERROR_ITEMS_LIMIT)

        for file_item in files:
            item_id = str(getattr(file_item, "id", ""))
            item_name = str(getattr(file_item, "name", item_id))
            ext = (
                (getattr(file_item, "extension", None) or _file_extension(item_name))
                .lower()
                .strip(".")
            )
            try:
                if ext not in SUPPORTED_IMAGE_EXTENSIONS:
                    stats["skipped"] += 1
                    await self._upsert_raw_result(
                        account_id=account.id,
                        item_id=item_id,
                        status="skipped",
                        suggested_category="unsupported_format",
                        confidence=0.0,
                        detected_objects=[],
                        entities=[],
                        technical_metadata={"extension": ext or None},
                        ocr_text=None,
                        processing_ms=0,
                        model_version=self.pipeline.model_version,
                        error=f"Unsupported extension: {ext or 'none'}",
                    )
                    continue

                if not reprocess and await self._has_existing_analysis(account.id, item_id):
                    stats["skipped"] += 1
                    await self._upsert_raw_result(
                        account_id=account.id,
                        item_id=item_id,
                        status="skipped",
                        suggested_category="already_analyzed",
                        confidence=0.0,
                        detected_objects=[],
                        entities=[],
                        technical_metadata={"extension": ext},
                        ocr_text=None,
                        processing_ms=0,
                        model_version=self.pipeline.model_version,
                        error="Item already analyzed",
                    )
                    continue

                if await self._has_conflicting_metadata(account.id, item_id, category_id):
                    stats["skipped"] += 1
                    await self._upsert_raw_result(
                        account_id=account.id,
                        item_id=item_id,
                        status="skipped",
                        suggested_category="already_mapped_other_category",
                        confidence=0.0,
                        detected_objects=[],
                        entities=[],
                        technical_metadata={"extension": ext},
                        ocr_text=None,
                        processing_ms=0,
                        model_version=self.pipeline.model_version,
                        error="Item already mapped to another metadata category",
                    )
                    continue

                analysis = await self._analyze_item_bytes(client, account, item_id, item_name)
                await self._upsert_raw_result(
                    account_id=account.id,
                    item_id=item_id,
                    status=analysis.status,
                    suggested_category=analysis.suggested_category,
                    confidence=analysis.confidence,
                    detected_objects=analysis.objects,
                    entities=analysis.entities,
                    technical_metadata=analysis.technical_metadata,
                    ocr_text=analysis.ocr_text,
                    processing_ms=analysis.processing_ms,
                    model_version=analysis.model_version,
                    error=analysis.error,
                )
                values = self._build_metadata_values(analysis=analysis, attr_ids=attr_ids)
                await apply_metadata_change(
                    self.session,
                    account_id=account.id,
                    item_id=item_id,
                    category_id=category_id,
                    values=values,
                    batch_id=batch_id,
                    job_id=job_id,
                )
                stats["mapped"] += 1
            except UnsupportedImageError as exc:
                stats["skipped"] += 1
                error_collector.record(
                    reason=str(exc),
                    item_id=item_id,
                    item_name=item_name,
                    stage="image_decode",
                )
                await self._upsert_raw_result(
                    account_id=account.id,
                    item_id=item_id,
                    status="skipped",
                    suggested_category="decode_error",
                    confidence=0.0,
                    detected_objects=[],
                    entities=[],
                    technical_metadata={"extension": ext},
                    ocr_text=None,
                    processing_ms=0,
                    model_version=self.pipeline.model_version,
                    error=str(exc),
                )
            except Exception as exc:
                stats["failed"] += 1
                error_collector.record(
                    reason=str(exc),
                    item_id=item_id,
                    item_name=item_name,
                    stage="analyze_image",
                )
                await self._upsert_raw_result(
                    account_id=account.id,
                    item_id=item_id,
                    status="failed",
                    suggested_category=None,
                    confidence=0.0,
                    detected_objects=[],
                    entities=[],
                    technical_metadata={"extension": ext},
                    ocr_text=None,
                    processing_ms=0,
                    model_version=self.pipeline.model_version,
                    error=str(exc),
                )
            finally:
                stats["processed"] += 1
                if progress_reporter is not None:
                    await progress_reporter.increment()
                    if progress_reporter.current % 5 == 0:
                        await progress_reporter.update_metrics(
                            processed=stats["processed"],
                            mapped=stats["mapped"],
                            skipped=stats["skipped"],
                            failed=stats["failed"],
                            error_items=stats.get("error_items", []),
                            error_items_truncated=stats.get("error_items_truncated", 0),
                        )

        await self.session.commit()
        return stats

    async def _analyze_item_bytes(
        self,
        client: DriveProviderClient,
        account: LinkedAccount,
        item_id: str,
        item_name: str,
    ):
        temp_dir = tempfile.mkdtemp(prefix="image_analysis_")
        target = str(Path(temp_dir) / item_name)
        try:
            await client.download_file_to_path(
                account,
                item_id,
                target,
                timeout_seconds=float(self.settings.image_analysis_timeout_seconds),
            )
            data = Path(target).read_bytes()
            return self.pipeline.analyze(image_bytes=data, filename=item_name)
        except ImageAnalysisError:
            raise
        except Exception as exc:
            raise ImageAnalysisError(str(exc)) from exc
        finally:
            try:
                Path(target).unlink(missing_ok=True)
                Path(temp_dir).rmdir()
            except Exception:
                pass

    async def _has_existing_analysis(self, account_id: UUID, item_id: str) -> bool:
        stmt = select(ImageAnalysisResultRow.id).where(
            ImageAnalysisResultRow.account_id == account_id,
            ImageAnalysisResultRow.item_id == item_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def _has_conflicting_metadata(
        self, account_id: UUID, item_id: str, category_id: UUID
    ) -> bool:
        stmt = select(ItemMetadata.category_id).where(
            ItemMetadata.account_id == account_id,
            ItemMetadata.item_id == item_id,
        )
        existing_category_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if not existing_category_id:
            return False
        return existing_category_id != category_id

    async def _upsert_raw_result(
        self,
        *,
        account_id: UUID,
        item_id: str,
        status: str,
        suggested_category: str | None,
        confidence: float,
        detected_objects: list[dict],
        entities: list[str],
        technical_metadata: dict,
        ocr_text: str | None,
        processing_ms: int,
        model_version: str,
        error: str | None,
    ) -> None:
        stmt = select(ImageAnalysisResultRow).where(
            ImageAnalysisResultRow.account_id == account_id,
            ImageAnalysisResultRow.item_id == item_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            self.session.add(
                ImageAnalysisResultRow(
                    account_id=account_id,
                    item_id=item_id,
                    status=status,
                    suggested_category=suggested_category,
                    confidence=confidence,
                    detected_objects=detected_objects,
                    entities=entities,
                    technical_metadata=technical_metadata,
                    ocr_text=ocr_text,
                    processing_ms=processing_ms,
                    model_version=model_version,
                    error=error,
                )
            )
            return

        existing.status = status
        existing.suggested_category = suggested_category
        existing.confidence = confidence
        existing.detected_objects = detected_objects
        existing.entities = entities
        existing.technical_metadata = technical_metadata
        existing.ocr_text = ocr_text
        existing.processing_ms = processing_ms
        existing.model_version = model_version
        existing.error = error

    def _build_metadata_values(self, *, analysis, attr_ids: dict[str, str]) -> dict[str, Any]:
        values: dict[str, Any] = {}

        threshold = float(self.settings.image_analysis_confidence_threshold)
        resolved_label = (
            analysis.suggested_category
            if float(analysis.confidence or 0.0) >= threshold
            else "unclassified"
        )

        def set_if_exists(field_key: str, value: Any) -> None:
            attr_id = attr_ids.get(field_key)
            if not attr_id:
                return
            if value is None:
                return
            values[attr_id] = value

        set_if_exists("classification_label", resolved_label)
        set_if_exists("classification_confidence", analysis.confidence)
        set_if_exists("objects", [obj.get("label") for obj in analysis.objects if obj.get("label")])
        set_if_exists("entities", analysis.entities)
        set_if_exists("ocr_text", analysis.ocr_text)
        set_if_exists("image_width", analysis.technical_metadata.get("image_width"))
        set_if_exists("image_height", analysis.technical_metadata.get("image_height"))
        set_if_exists("capture_datetime", analysis.technical_metadata.get("capture_datetime"))
        set_if_exists("camera_make", analysis.technical_metadata.get("camera_make"))
        set_if_exists("camera_model", analysis.technical_metadata.get("camera_model"))
        set_if_exists("gps_latitude", analysis.technical_metadata.get("gps_latitude"))
        set_if_exists("gps_longitude", analysis.technical_metadata.get("gps_longitude"))
        set_if_exists("dominant_colors", analysis.technical_metadata.get("dominant_colors"))
        set_if_exists("analysis_model_version", analysis.model_version)
        return values

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
