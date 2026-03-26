from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.services.metadata_libraries.comics import (
    reader_session_service as reader_service,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _account():
    return SimpleNamespace(id=uuid4())


def _item(name: str = "Saga.cbz"):
    return SimpleNamespace(
        id="item-1",
        name=name,
        item_type="file",
        modified_at=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
        size=4096,
    )


def _metadata_session(plugin_key: str | None):
    return SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(plugin_key)),
    )


def _graph_client(item):
    async def _download_file_to_path(_account, _item_id, target_path, timeout_seconds=None):
        _ = timeout_seconds
        Path(target_path).write_bytes(b"archive-bytes")
        return item.name

    return SimpleNamespace(
        get_item_metadata=AsyncMock(return_value=item),
        download_file_to_path=AsyncMock(side_effect=_download_file_to_path),
    )


def _extract_pages_factory(page_payloads: list[tuple[str, bytes, int | None, int | None]]):
    def _extract_pages(local_path: str, extension: str, output_dir: str):
        assert Path(local_path).exists()
        assert extension
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        pages = []
        for index, (filename, content, width, height) in enumerate(page_payloads):
            page_path = Path(output_dir) / filename
            page_path.write_bytes(content)
            pages.append(
                SimpleNamespace(
                    index=index,
                    filename=filename,
                    width=width,
                    height=height,
                )
            )
        return pages

    return _extract_pages


@pytest.mark.asyncio
async def test_create_session_returns_manifest_and_page_payload(monkeypatch):
    await reader_service.clear_comic_reader_sessions()
    session = _metadata_session("comics_core")
    account = _account()
    item = _item()
    graph_client = _graph_client(item)
    service = reader_service.ComicReaderSessionService(session)
    monkeypatch.setattr(
        reader_service,
        "extract_comic_pages",
        _extract_pages_factory(
            [
                ("page-0001.jpg", b"cover-page", 800, 1200),
                ("page-0002.jpg", b"page-two", 810, 1210),
            ]
        ),
    )

    reader_session = await service.create_session(
        account_id=account.id,
        item_id=item.id,
        account=account,
        graph_client=graph_client,
    )

    assert reader_session.page_count == 2
    assert reader_session.cache_hit is False
    assert [page.index for page in reader_session.pages] == [0, 1]
    assert reader_session.pages[0].width == 800

    payload = await service.get_page_payload(
        account_id=account.id,
        session_id=reader_session.session_id,
        page_index=1,
    )
    assert payload.media_type == "image/jpeg"
    assert Path(payload.path).read_bytes() == b"page-two"

    await reader_service.clear_comic_reader_sessions()


@pytest.mark.asyncio
async def test_create_session_reuses_cached_extraction(monkeypatch):
    await reader_service.clear_comic_reader_sessions()
    session = _metadata_session("comics_core")
    account = _account()
    item = _item()
    graph_client = _graph_client(item)
    service = reader_service.ComicReaderSessionService(session)
    extract_calls = []

    def _tracked_extract(local_path: str, extension: str, output_dir: str):
        extract_calls.append((local_path, extension, output_dir))
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / "page-0001.jpg").write_bytes(b"cover")
        return [SimpleNamespace(index=0, filename="page-0001.jpg", width=800, height=1200)]

    monkeypatch.setattr(reader_service, "extract_comic_pages", _tracked_extract)

    first = await service.create_session(
        account_id=account.id,
        item_id=item.id,
        account=account,
        graph_client=graph_client,
    )
    second = await service.create_session(
        account_id=account.id,
        item_id=item.id,
        account=account,
        graph_client=graph_client,
    )

    assert first.session_id == second.session_id
    assert second.cache_hit is True
    assert graph_client.download_file_to_path.await_count == 1
    assert len(extract_calls) == 1

    await reader_service.clear_comic_reader_sessions()


@pytest.mark.asyncio
async def test_create_session_rejects_item_without_comics_metadata():
    await reader_service.clear_comic_reader_sessions()
    session = _metadata_session(None)
    account = _account()
    item = _item()
    graph_client = _graph_client(item)
    service = reader_service.ComicReaderSessionService(session)

    with pytest.raises(
        reader_service.ComicReaderValidationError,
        match="comics metadata library",
    ):
        await service.create_session(
            account_id=account.id,
            item_id=item.id,
            account=account,
            graph_client=graph_client,
        )


@pytest.mark.asyncio
async def test_create_session_rejects_pdf_and_epub_reader_inputs():
    await reader_service.clear_comic_reader_sessions()
    session = _metadata_session("comics_core")
    account = _account()

    for filename in ("Saga.pdf", "Saga.epub"):
        service = reader_service.ComicReaderSessionService(session)
        graph_client = _graph_client(_item(filename))
        with pytest.raises(
            reader_service.ComicReaderValidationError,
            match="archive comics only in v1",
        ):
            await service.create_session(
                account_id=account.id,
                item_id="item-1",
                account=account,
                graph_client=graph_client,
            )


@pytest.mark.asyncio
async def test_get_page_payload_expires_sessions(monkeypatch):
    await reader_service.clear_comic_reader_sessions()
    session = _metadata_session("comics_core")
    account = _account()
    item = _item()
    graph_client = _graph_client(item)
    service = reader_service.ComicReaderSessionService(session)
    monkeypatch.setattr(
        reader_service,
        "extract_comic_pages",
        _extract_pages_factory([("page-0001.jpg", b"cover-page", 800, 1200)]),
    )

    reader_session = await service.create_session(
        account_id=account.id,
        item_id=item.id,
        account=account,
        graph_client=graph_client,
    )
    reader_service._reader_sessions_by_id[reader_session.session_id].expires_at = (
        datetime.now(UTC) - timedelta(seconds=1)
    )

    with pytest.raises(
        reader_service.ComicReaderSessionNotFoundError,
        match="session not found",
    ):
        await service.get_page_payload(
            account_id=account.id,
            session_id=reader_session.session_id,
            page_index=0,
        )

    await reader_service.clear_comic_reader_sessions()
