from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.services import auto_metadata_mapper as amm


@pytest.mark.asyncio
async def test_enqueue_auto_mapping_jobs_skips_pdf_for_books_and_comics(monkeypatch):
    created: list[tuple[str, list[str]]] = []

    async def fake_enqueue_job_command(session, *, job_type, payload, dedupe_key=None):  # noqa: ARG001
        created.append((job_type, list(payload.get("item_ids", []))))
        return SimpleNamespace(id=uuid4())

    class _FakeLibraryService:
        def __init__(self, session):  # noqa: ARG002
            pass

        async def get_active_comics_category(self):
            return object()

        async def get_active_books_category(self):
            return object()

        async def get_active_images_category(self):
            return None

    monkeypatch.setattr(amm, "enqueue_job_command", fake_enqueue_job_command)
    monkeypatch.setattr(amm, "MetadataLibraryService", _FakeLibraryService)

    summary = await amm.enqueue_auto_mapping_jobs(
        session=object(),
        account_id=uuid4(),
        candidates=[
            amm.AutoMapCandidate(item_id="pdf-1", name="doc.pdf", extension="pdf"),
            amm.AutoMapCandidate(item_id="epub-1", name="book.epub", extension="epub"),
            amm.AutoMapCandidate(item_id="cbz-1", name="comic.cbz", extension="cbz"),
        ],
        source="sync",
        chunk_size=500,
    )

    assert summary["items_by_type"] == {
        "extract_book_assets": 1,
        "extract_comic_assets": 1,
    }
    assert summary["total_jobs"] == 2
    assert ("extract_book_assets", ["epub-1"]) in created
    assert ("extract_comic_assets", ["cbz-1"]) in created


@pytest.mark.asyncio
async def test_enqueue_auto_mapping_jobs_pdf_only_creates_no_jobs(monkeypatch):
    async def fake_enqueue_job_command(session, *, job_type, payload, dedupe_key=None):  # noqa: ARG001
        raise AssertionError("enqueue_job_command should not be called for PDF-only auto mapping")

    class _FakeLibraryService:
        def __init__(self, session):  # noqa: ARG002
            pass

        async def get_active_comics_category(self):
            return object()

        async def get_active_books_category(self):
            return object()

        async def get_active_images_category(self):
            return None

    monkeypatch.setattr(amm, "enqueue_job_command", fake_enqueue_job_command)
    monkeypatch.setattr(amm, "MetadataLibraryService", _FakeLibraryService)

    summary = await amm.enqueue_auto_mapping_jobs(
        session=object(),
        account_id=uuid4(),
        candidates=[amm.AutoMapCandidate(item_id="pdf-1", name="doc.pdf", extension="pdf")],
        source="upload",
    )

    assert summary["items_by_type"] == {}
    assert summary["total_jobs"] == 0
    assert summary["job_ids"] == []
