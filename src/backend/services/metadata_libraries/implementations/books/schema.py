"""Books metadata-library schema definition."""

from __future__ import annotations

from dataclasses import dataclass

BOOKS_LIBRARY_KEY = "books_core"


@dataclass(frozen=True, slots=True)
class MetadataLibraryFieldSpec:
    key: str
    name: str
    data_type: str
    is_required: bool = False


BOOKS_LIBRARY_FIELDS: list[MetadataLibraryFieldSpec] = [
    MetadataLibraryFieldSpec("title", "Title", "text"),
    MetadataLibraryFieldSpec("subtitle", "Subtitle", "text"),
    MetadataLibraryFieldSpec("author", "Author", "text"),
    MetadataLibraryFieldSpec("publisher", "Publisher", "text"),
    MetadataLibraryFieldSpec("published_year", "Published Year", "number"),
    MetadataLibraryFieldSpec("isbn", "ISBN", "text"),
    MetadataLibraryFieldSpec("language", "Language", "text"),
    MetadataLibraryFieldSpec("page_count", "Page Count", "number"),
    MetadataLibraryFieldSpec("genre", "Genre", "tags"),
    MetadataLibraryFieldSpec("summary", "Summary", "text"),
    MetadataLibraryFieldSpec("cover_item_id", "Cover Item ID", "text"),
    MetadataLibraryFieldSpec("cover_account_id", "Cover Account ID", "text"),
    MetadataLibraryFieldSpec("cover_filename", "Cover Filename", "text"),
    MetadataLibraryFieldSpec("file_format", "File Format", "text"),
]
