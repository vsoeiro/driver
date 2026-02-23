"""Comics metadata-library implementation."""

from backend.services.metadata_libraries.implementations.comics.schema import (
    COMICS_LIBRARY_FIELDS,
    COMICS_LIBRARY_KEY,
    MetadataLibraryFieldSpec,
)

__all__ = [
    "COMICS_LIBRARY_KEY",
    "COMICS_LIBRARY_FIELDS",
    "MetadataLibraryFieldSpec",
]

