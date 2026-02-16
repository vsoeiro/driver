"""Comic extraction and metadata mapping helpers."""

from __future__ import annotations

import posixpath
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LinkedAccount
from backend.services.metadata_plugins import MetadataPluginService
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.providers.base import DriveProviderClient
from backend.services.providers.factory import build_drive_client
from backend.services.token_manager import TokenManager

SUPPORTED_COMIC_EXTENSIONS = {"cbz", "zip", "pdf", "epub"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}
COVER_STORAGE_FOLDER = "__driver_comic_covers__"


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
    if ext in {"zip", "cbz"}:
        return _extract_from_zip(local_path, fmt=ext)
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
        image_names.sort(key=lambda value: value.lower())

        if not image_names:
            raise ValueError("Archive has no image pages")

        cover_name = image_names[0]
        cover_bytes = archive.read(cover_name)
        cover_extension = Path(cover_name).suffix.lower().lstrip(".") or "jpg"
        return ComicExtractionResult(
            format=fmt,
            page_count=len(image_names),
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
    return ComicExtractionResult(
        format="pdf",
        page_count=len(reader.pages),
        cover_bytes=None,
        cover_extension=None,
        details={"cover": "not_extracted_in_v1"},
    )


class ComicMetadataService:
    """Extract comic data and map into ItemMetadata values."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process_item_ids(self, account_id, item_ids: list[str], *, job_id=None, batch_id=None) -> dict[str, int]:
        account = await self.session.get(LinkedAccount, account_id)
        if not account:
            raise ValueError("Account not found")

        plugin_service = MetadataPluginService(self.session)
        category = await plugin_service.ensure_active_comic_category()
        attr_ids = await plugin_service.comic_attribute_id_map()

        token_manager = TokenManager(self.session)
        client = build_drive_client(account, token_manager)

        files_to_process = await self._expand_items(client, account, item_ids)
        stats = {"total": len(files_to_process), "mapped": 0, "skipped": 0, "failed": 0}

        cover_folder_id = await self._ensure_cover_folder(client, account)
        for file_item in files_to_process:
            try:
                mapped = await self._process_single_file(
                    client=client,
                    account=account,
                    item=file_item,
                    cover_folder_id=cover_folder_id,
                    category_id=category.id,
                    attr_ids=attr_ids,
                    job_id=job_id,
                    batch_id=batch_id,
                )
                if mapped:
                    stats["mapped"] += 1
                else:
                    stats["skipped"] += 1
            except Exception:
                stats["failed"] += 1

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

    async def _ensure_cover_folder(self, client: DriveProviderClient, account: LinkedAccount) -> str:
        root = await client.list_root_items(account)
        for item in root.items:
            if item.item_type == "folder" and item.name == COVER_STORAGE_FOLDER:
                return item.id

        folder = await client.create_folder(
            account,
            COVER_STORAGE_FOLDER,
            parent_id="root",
            conflict_behavior="rename",
        )
        return folder.id

    async def _process_single_file(
        self,
        *,
        client: DriveProviderClient,
        account: LinkedAccount,
        item: Any,
        cover_folder_id: str,
        category_id,
        attr_ids: dict[str, str],
        job_id,
        batch_id,
    ) -> bool:
        ext = file_extension(item.name)
        if ext not in SUPPORTED_COMIC_EXTENSIONS:
            return False

        temp_dir = tempfile.mkdtemp(prefix="comic_extract_")
        local_path = str(Path(temp_dir) / f"{item.id}.{ext or 'bin'}")
        try:
            await client.download_file_to_path(account, item.id, local_path)
            extraction = extract_comic_asset(local_path, ext)
            mapped_values = self._build_metadata_values(item=item, extraction=extraction, attr_ids=attr_ids)

            if extraction.cover_bytes:
                cover_ext = extraction.cover_extension or "jpg"
                upload_name = f"{item.id}.{cover_ext}"
                uploaded = await client.upload_small_file(
                    account,
                    upload_name,
                    extraction.cover_bytes,
                    cover_folder_id,
                )
                cover_id_attr = attr_ids.get("cover_item_id")
                cover_name_attr = attr_ids.get("cover_filename")
                if cover_id_attr:
                    mapped_values[cover_id_attr] = uploaded.id
                if cover_name_attr:
                    mapped_values[cover_name_attr] = uploaded.name

            await apply_metadata_change(
                self.session,
                account_id=account.id,
                item_id=item.id,
                category_id=category_id,
                values=mapped_values,
                batch_id=batch_id,
                job_id=job_id,
            )
            return True
        except Exception:
            return False
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
        set_if_exists("file_size", item.size)
        set_if_exists("file_format", extraction.format)
        set_if_exists("page_count", extraction.page_count)
        return values
