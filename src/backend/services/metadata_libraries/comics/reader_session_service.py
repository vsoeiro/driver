"""Temporary comic reader sessions backed by extracted pages on disk."""

from __future__ import annotations

import asyncio
import mimetypes
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ItemMetadata, MetadataCategory
from backend.schemas.drive import ComicReaderPage, ComicReaderSession
from backend.services.metadata_libraries.comics.archive_reader import (
    READER_COMIC_EXTENSIONS,
    extract_comic_pages,
    file_extension,
)
from backend.services.metadata_libraries.implementations.comics.schema import (
    COMICS_LIBRARY_KEY,
)
from backend.services.providers.base import DriveProviderClient

COMIC_READER_SESSION_TTL = timedelta(minutes=15)


class ComicReaderValidationError(ValueError):
    """Raised when an item cannot be opened in the comic reader."""


class ComicReaderSessionNotFoundError(LookupError):
    """Raised when a session or page is missing or expired."""


@dataclass(slots=True)
class ComicReaderPagePayload:
    """Resolved page payload for route responses."""

    path: str
    media_type: str


@dataclass(slots=True)
class _ComicReaderSessionEntry:
    session_id: str
    cache_key: str
    account_id: str
    item_id: str
    item_name: str
    extension: str
    root_dir: str
    pages_dir: str
    page_filenames: list[str]
    pages: list[ComicReaderPage]
    expires_at: datetime


_reader_sessions_by_id: dict[str, _ComicReaderSessionEntry] = {}
_reader_session_ids_by_cache_key: dict[str, str] = {}
_reader_sessions_lock: asyncio.Lock | None = None


async def clear_comic_reader_sessions() -> None:
    """Clear cached reader sessions, used by tests and maintenance."""
    global _reader_sessions_lock
    if _reader_sessions_lock is None:
        _reader_sessions_lock = asyncio.Lock()
    async with _reader_sessions_lock:
        entries = list(_reader_sessions_by_id.values())
        _reader_sessions_by_id.clear()
        _reader_session_ids_by_cache_key.clear()
    for entry in entries:
        await asyncio.to_thread(shutil.rmtree, entry.root_dir, True)


class ComicReaderSessionService:
    """Create and resolve temporary comic reader sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        account_id: UUID | str,
        item_id: str,
        account,
        graph_client: DriveProviderClient,
    ) -> ComicReaderSession:
        await self._ensure_comics_metadata(account_id=account_id, item_id=item_id)
        item = await graph_client.get_item_metadata(account, item_id)
        if getattr(item, "item_type", None) != "file":
            raise ComicReaderValidationError("Comic reader supports files only")

        extension = file_extension(getattr(item, "name", None))
        if extension not in READER_COMIC_EXTENSIONS:
            raise ComicReaderValidationError(
                f"Comic reader supports archive comics only in v1. Unsupported extension: .{extension or 'unknown'}"
            )

        cache_key = self._cache_key(
            account_id=account_id,
            item_id=item_id,
            modified_at=getattr(item, "modified_at", None),
            size=getattr(item, "size", None),
        )

        lock = await self._get_lock()
        async with lock:
            await self._cleanup_expired_locked(now=self._utc_now())
            cached_entry = self._get_cached_entry_locked(cache_key=cache_key)
            if cached_entry is not None:
                self._refresh_entry_ttl_locked(cached_entry)
                return self._serialize_session(cached_entry, cache_hit=True)

            entry = await self._build_session_entry(
                account_id=account_id,
                cache_key=cache_key,
                item=item,
                account=account,
                graph_client=graph_client,
                extension=extension,
            )
            _reader_sessions_by_id[entry.session_id] = entry
            _reader_session_ids_by_cache_key[cache_key] = entry.session_id
            return self._serialize_session(entry, cache_hit=False)

    async def get_page_payload(
        self,
        *,
        account_id: UUID | str,
        session_id: str,
        page_index: int,
    ) -> ComicReaderPagePayload:
        lock = await self._get_lock()
        async with lock:
            await self._cleanup_expired_locked(now=self._utc_now())
            entry = _reader_sessions_by_id.get(session_id)
            if entry is None or entry.account_id != str(account_id):
                raise ComicReaderSessionNotFoundError("Comic reader session not found")
            if page_index < 0 or page_index >= len(entry.pages):
                raise ComicReaderSessionNotFoundError("Comic reader page not found")

            page_path = Path(entry.pages_dir) / entry.page_filenames[page_index]
            if not page_path.exists():
                raise ComicReaderSessionNotFoundError("Comic reader page not found")

            self._refresh_entry_ttl_locked(entry)
            media_type = mimetypes.guess_type(page_path.name)[0] or "application/octet-stream"
            return ComicReaderPagePayload(path=str(page_path), media_type=media_type)

    async def _ensure_comics_metadata(
        self,
        *,
        account_id: UUID | str,
        item_id: str,
    ) -> None:
        stmt = (
            select(MetadataCategory.plugin_key)
            .select_from(ItemMetadata)
            .join(MetadataCategory, MetadataCategory.id == ItemMetadata.category_id)
            .where(
                ItemMetadata.account_id == account_id,
                ItemMetadata.item_id == item_id,
            )
        )
        plugin_key = (await self.session.execute(stmt)).scalar_one_or_none()
        if plugin_key != COMICS_LIBRARY_KEY:
            raise ComicReaderValidationError(
                "Item is not mapped to the comics metadata library"
            )

    async def _build_session_entry(
        self,
        *,
        account_id: UUID | str,
        cache_key: str,
        item,
        account,
        graph_client: DriveProviderClient,
        extension: str,
    ) -> _ComicReaderSessionEntry:
        root_dir = tempfile.mkdtemp(prefix="comic_reader_")
        archive_path = Path(root_dir) / f"source.{extension}"
        pages_dir = Path(root_dir) / "pages"

        try:
            await graph_client.download_file_to_path(
                account,
                item.id,
                str(archive_path),
            )
            extracted_pages = await asyncio.to_thread(
                extract_comic_pages,
                str(archive_path),
                extension,
                str(pages_dir),
            )
            archive_path.unlink(missing_ok=True)
        except Exception:
            await asyncio.to_thread(shutil.rmtree, root_dir, True)
            raise

        expires_at = self._utc_now() + COMIC_READER_SESSION_TTL
        return _ComicReaderSessionEntry(
            session_id=uuid4().hex,
            cache_key=cache_key,
            account_id=str(account_id),
            item_id=str(item.id),
            item_name=str(getattr(item, "name", "") or item.id),
            extension=extension,
            root_dir=root_dir,
            pages_dir=str(pages_dir),
            page_filenames=[page.filename for page in extracted_pages],
            pages=[
                ComicReaderPage(
                    index=page.index,
                    width=page.width,
                    height=page.height,
                )
                for page in extracted_pages
            ],
            expires_at=expires_at,
        )

    async def _cleanup_expired_locked(self, *, now: datetime) -> None:
        expired_entries = [
            entry
            for entry in _reader_sessions_by_id.values()
            if entry.expires_at <= now
        ]
        if not expired_entries:
            return

        for entry in expired_entries:
            _reader_sessions_by_id.pop(entry.session_id, None)
            if _reader_session_ids_by_cache_key.get(entry.cache_key) == entry.session_id:
                _reader_session_ids_by_cache_key.pop(entry.cache_key, None)

        for entry in expired_entries:
            await asyncio.to_thread(shutil.rmtree, entry.root_dir, True)

    def _get_cached_entry_locked(self, *, cache_key: str) -> _ComicReaderSessionEntry | None:
        session_id = _reader_session_ids_by_cache_key.get(cache_key)
        if not session_id:
            return None
        entry = _reader_sessions_by_id.get(session_id)
        if entry is None:
            _reader_session_ids_by_cache_key.pop(cache_key, None)
            return None
        if not Path(entry.pages_dir).exists():
            _reader_sessions_by_id.pop(session_id, None)
            _reader_session_ids_by_cache_key.pop(cache_key, None)
            return None
        return entry

    def _refresh_entry_ttl_locked(self, entry: _ComicReaderSessionEntry) -> None:
        entry.expires_at = self._utc_now() + COMIC_READER_SESSION_TTL

    def _serialize_session(
        self,
        entry: _ComicReaderSessionEntry,
        *,
        cache_hit: bool,
    ) -> ComicReaderSession:
        return ComicReaderSession(
            session_id=entry.session_id,
            item_id=entry.item_id,
            item_name=entry.item_name,
            extension=entry.extension,
            page_count=len(entry.pages),
            pages=[page.model_copy(deep=True) for page in entry.pages],
            expires_at=entry.expires_at,
            cache_hit=cache_hit,
        )

    @staticmethod
    def _cache_key(
        *,
        account_id: UUID | str,
        item_id: str,
        modified_at,
        size,
    ) -> str:
        modified_value = modified_at
        if isinstance(modified_value, datetime):
            if modified_value.tzinfo is None:
                modified_value = modified_value.replace(tzinfo=UTC)
            modified_token = modified_value.isoformat()
        else:
            modified_token = str(modified_value or "")
        return f"{account_id}:{item_id}:{modified_token}:{size or 0}"

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    async def _get_lock() -> asyncio.Lock:
        global _reader_sessions_lock
        if _reader_sessions_lock is None:
            _reader_sessions_lock = asyncio.Lock()
        return _reader_sessions_lock
