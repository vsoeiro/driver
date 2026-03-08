import zipfile

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
