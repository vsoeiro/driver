"""Comics metadata-library schema definition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COMICS_LIBRARY_KEY = "comics_core"


@dataclass(frozen=True, slots=True)
class MetadataLibraryFieldSpec:
    key: str
    name: str
    data_type: str
    is_required: bool = False
    options: dict[str, Any] | None = None


COMICS_LIBRARY_FIELDS: list[MetadataLibraryFieldSpec] = [
    MetadataLibraryFieldSpec("series", "Series", "text"),
    MetadataLibraryFieldSpec("volume", "Volume", "number"),
    MetadataLibraryFieldSpec("issue_number", "Issue Number", "text"),
    MetadataLibraryFieldSpec("max_volumes", "Max Volumes", "number"),
    MetadataLibraryFieldSpec("max_issues", "Max Issues", "number"),
    MetadataLibraryFieldSpec(
        "series_status",
        "Series Status",
        "select",
        options={"options": ["ongoing", "completed", "hiatus", "cancelled", "unknown"]},
    ),
    MetadataLibraryFieldSpec("title", "Title", "text"),
    MetadataLibraryFieldSpec("year", "Year", "number"),
    MetadataLibraryFieldSpec("month", "Month", "number"),
    MetadataLibraryFieldSpec("publisher", "Publisher", "text"),
    MetadataLibraryFieldSpec("imprint", "Imprint", "text"),
    MetadataLibraryFieldSpec("writer", "Writer", "text"),
    MetadataLibraryFieldSpec("penciller", "Penciller", "text"),
    MetadataLibraryFieldSpec("colorist", "Colorist", "text"),
    MetadataLibraryFieldSpec("letterer", "Letterer", "text"),
    MetadataLibraryFieldSpec("genre", "Genre", "text"),
    MetadataLibraryFieldSpec("language", "Language", "text"),
    MetadataLibraryFieldSpec("original_language", "Original Language", "text"),
    MetadataLibraryFieldSpec("tags", "Tags", "tags"),
    MetadataLibraryFieldSpec("summary", "Summary", "text"),
    MetadataLibraryFieldSpec("cover_item_id", "Cover Item ID", "text"),
    MetadataLibraryFieldSpec("cover_account_id", "Cover Account ID", "text"),
    MetadataLibraryFieldSpec("cover_filename", "Cover Filename", "text"),
    MetadataLibraryFieldSpec("page_count", "Page Count", "number"),
    MetadataLibraryFieldSpec("file_format", "File Format", "text"),
]

