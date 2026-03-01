"""Metadata library services."""

from backend.services.metadata_libraries.implementations.books.schema import BOOKS_LIBRARY_KEY
from backend.services.metadata_libraries.implementations.comics.schema import COMICS_LIBRARY_KEY
from backend.services.metadata_libraries.service import MetadataLibraryService
from backend.services.metadata_libraries.settings import MetadataLibrarySettingsService

__all__ = [
    "BOOKS_LIBRARY_KEY",
    "COMICS_LIBRARY_KEY",
    "MetadataLibraryService",
    "MetadataLibrarySettingsService",
]
