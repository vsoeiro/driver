"""Compatibility facade for legacy metadata plugin imports.

Prefer importing from ``backend.services.metadata_libraries.service``.
"""

from backend.services.metadata_libraries.implementations.comics.schema import (
    COMICS_LIBRARY_FIELDS as COMIC_PLUGIN_FIELDS,
    COMICS_LIBRARY_KEY,
    MetadataLibraryFieldSpec as PluginFieldSpec,
)
from backend.services.metadata_libraries.service import (
    MetadataLibraryService as MetadataPluginService,
)

__all__ = [
    "COMICS_LIBRARY_KEY",
    "COMIC_PLUGIN_FIELDS",
    "PluginFieldSpec",
    "MetadataPluginService",
]

