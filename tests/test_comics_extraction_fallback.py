import zipfile

import pytest

from backend.services import comics


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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipFile("File is not a zip file")),
    )
    monkeypatch.setattr(comics, "_detect_archive_container", lambda *_args, **_kwargs: "rar")
    monkeypatch.setattr(comics, "_run_container_extractor", lambda *_args, **_kwargs: _sample_result("cbz"))

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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipFile("File is not a zip file")),
    )
    monkeypatch.setattr(comics, "_detect_archive_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        comics,
        "_run_container_extractor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("container extractor failed")),
    )
    monkeypatch.setattr(comics, "_extract_from_rar_with_7z", lambda *_args, **_kwargs: _sample_result("cbz"))

    result = comics.extract_comic_asset("dummy.cbz", "cbz")

    assert result.format == "cbz"
    assert result.details["fallback_used"] == "7z_cli"
    assert result.details["primary_container"] == "zip"


def test_cbz_fallback_uses_detected_pdf(monkeypatch):
    monkeypatch.setattr(
        comics,
        "_extract_from_zip",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipFile("File is not a zip file")),
    )
    monkeypatch.setattr(comics, "_detect_archive_container", lambda *_args, **_kwargs: "pdf")
    monkeypatch.setattr(comics, "_extract_from_pdf", lambda *_args, **_kwargs: _sample_result("pdf"))

    result = comics.extract_comic_asset("dummy.cbz", "cbz")

    assert result.format == "pdf"
    assert result.details["fallback_used"] == "pdf"
    assert result.details["detected_container"] == "pdf"
    assert result.details["primary_container"] == "zip"


def test_cbz_fallback_raises_when_all_extractors_fail(monkeypatch):
    monkeypatch.setattr(
        comics,
        "_extract_from_zip",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipFile("File is not a zip file")),
    )
    monkeypatch.setattr(comics, "_detect_archive_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        comics,
        "_run_container_extractor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("container extractor failed")),
    )
    monkeypatch.setattr(
        comics,
        "_extract_from_rar_with_7z",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("7z not available")),
    )

    with pytest.raises(ValueError, match="Archive extraction failed for \\.cbz"):
        comics.extract_comic_asset("dummy.cbz", "cbz")
