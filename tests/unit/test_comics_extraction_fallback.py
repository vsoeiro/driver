import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.services.metadata_libraries.comics import metadata_service as comics


def _sample_result(fmt: str) -> comics.ComicExtractionResult:
    return comics.ComicExtractionResult(
        format=fmt,
        page_count=12,
        cover_bytes=b"cover",
        cover_extension="jpg",
        details={},
    )


def test_cbz_fallback_uses_detected_rar(monkeypatch):
    monkeypatch.setattr(
        comics,
        "_extract_from_zip",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            zipfile.BadZipFile("File is not a zip file")
        ),
    )
    monkeypatch.setattr(
        comics, "_detect_archive_container", lambda *_args, **_kwargs: "rar"
    )
    monkeypatch.setattr(
        comics,
        "_run_container_extractor",
        lambda *_args, **_kwargs: _sample_result("cbz"),
    )

    result = comics.extract_comic_asset("dummy.cbz", "cbz")

    assert result.format == "cbz"
    assert result.page_count == 12
    assert result.details["fallback_used"] == "rar"
    assert result.details["detected_container"] == "rar"
    assert result.details["primary_container"] == "zip"


def test_cbz_fallback_uses_7z_cli_as_last_resort(monkeypatch):
    monkeypatch.setattr(
        comics,
        "_extract_from_zip",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            zipfile.BadZipFile("File is not a zip file")
        ),
    )
    monkeypatch.setattr(
        comics, "_detect_archive_container", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        comics,
        "_run_container_extractor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("container extractor failed")
        ),
    )
    monkeypatch.setattr(
        comics,
        "_extract_from_rar_with_7z",
        lambda *_args, **_kwargs: _sample_result("cbz"),
    )

    result = comics.extract_comic_asset("dummy.cbz", "cbz")

    assert result.format == "cbz"
    assert result.details["fallback_used"] == "rar_cli"
    assert result.details["primary_container"] == "zip"


def test_cbz_fallback_uses_detected_pdf(monkeypatch):
    monkeypatch.setattr(
        comics,
        "_extract_from_zip",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            zipfile.BadZipFile("File is not a zip file")
        ),
    )
    monkeypatch.setattr(
        comics, "_detect_archive_container", lambda *_args, **_kwargs: "pdf"
    )
    monkeypatch.setattr(
        comics, "_extract_from_pdf", lambda *_args, **_kwargs: _sample_result("pdf")
    )

    result = comics.extract_comic_asset("dummy.cbz", "cbz")

    assert result.format == "pdf"
    assert result.details["fallback_used"] == "pdf"
    assert result.details["detected_container"] == "pdf"
    assert result.details["primary_container"] == "zip"


def test_cbz_fallback_raises_when_all_extractors_fail(monkeypatch):
    monkeypatch.setattr(
        comics,
        "_extract_from_zip",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            zipfile.BadZipFile("File is not a zip file")
        ),
    )
    monkeypatch.setattr(
        comics, "_detect_archive_container", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        comics,
        "_run_container_extractor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("container extractor failed")
        ),
    )
    monkeypatch.setattr(
        comics,
        "_extract_from_rar_with_7z",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("7z not available")),
    )

    with pytest.raises(ValueError, match="Archive extraction failed for \\.cbz"):
        comics.extract_comic_asset("dummy.cbz", "cbz")


def test_pick_first_non_empty_payload_skips_empty():
    payloads = {
        "000.jpg": b"",
        "001.jpg": b"cover-bytes",
    }

    name, payload = comics._pick_first_non_empty_payload(
        ["000.jpg", "001.jpg"],
        reader=lambda candidate: payloads[candidate],
        source_label="ZIP",
    )

    assert name == "001.jpg"
    assert payload == b"cover-bytes"


def test_non_comic_extraction_error_recognizes_invalid_archive_messages():
    assert comics._is_non_comic_extraction_error(
        "RAR CLI extraction failed across available tools: 7za: code=2 stderr=ERROR: file.rar Cannot open the file as archive"
    )
    assert comics._is_non_comic_extraction_error("unrar: no image pages (stderr=)")


def test_non_comic_extraction_error_ignores_unrelated_errors():
    assert not comics._is_non_comic_extraction_error("Network timeout while downloading source file")


def test_existing_comic_mapping_skip_reason_detects_other_category():
    reason = comics._existing_comic_mapping_skip_reason(
        SimpleNamespace(category_id=uuid4(), values={}),
        category_id=uuid4(),
        attr_ids={},
    )

    assert reason == "Item already mapped to another metadata category"


def test_existing_comic_mapping_skip_reason_detects_existing_mapping_fields():
    category_id = uuid4()
    reason = comics._existing_comic_mapping_skip_reason(
        SimpleNamespace(category_id=category_id, values={"attr-cover": "cover-123"}),
        category_id=category_id,
        attr_ids={"cover_item_id": "attr-cover"},
    )

    assert reason == "Item already mapped"


@pytest.mark.asyncio
async def test_process_files_records_skip_reason_in_error_items(monkeypatch):
    session = AsyncMock()
    session.commit = AsyncMock()
    service = comics.ComicMetadataService(session)
    source_account_id = uuid4()
    target_account_id = uuid4()
    file_item = SimpleNamespace(id="item-1", name="broken.cbr")

    async def fake_ensure_cover_folder(*_args, **_kwargs):
        return "covers"

    async def fake_process_single_file(**_kwargs):
        return comics.ComicProcessOutcome(
            mapped=False,
            skip_reason="Skipped non-comic content: not a rar archive",
            skip_stage="extract_comic",
        )

    monkeypatch.setattr(service, "_ensure_cover_folder", fake_ensure_cover_folder)
    monkeypatch.setattr(service, "_process_single_file", fake_process_single_file)

    stats = service._init_stats(1)
    result = await service._process_files(
        files_to_process=[file_item],
        source_account=SimpleNamespace(id=source_account_id),
        source_client=object(),
        target_account=SimpleNamespace(id=target_account_id),
        target_client=object(),
        category_id=uuid4(),
        attr_ids={},
        plugin_settings=SimpleNamespace(
            storage_parent_folder_id="root",
            storage_folder_name="covers",
        ),
        stats=stats,
        job_id=None,
        batch_id=None,
        force_remap=False,
        progress_reporter=None,
    )

    assert result["mapped"] == 0
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert result["error_items"] == [
        {
            "reason": "Skipped non-comic content: not a rar archive",
            "item_id": "item-1",
            "item_name": "broken.cbr",
            "account_id": str(source_account_id),
            "stage": "extract_comic",
        }
    ]
    session.commit.assert_awaited_once()
