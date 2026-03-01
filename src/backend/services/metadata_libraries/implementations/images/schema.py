"""Images metadata-library schema definition."""

from __future__ import annotations

from dataclasses import dataclass

IMAGES_LIBRARY_KEY = "images_core"


@dataclass(frozen=True, slots=True)
class MetadataLibraryFieldSpec:
    key: str
    name: str
    data_type: str
    is_required: bool = False


IMAGES_LIBRARY_FIELDS: list[MetadataLibraryFieldSpec] = [
    MetadataLibraryFieldSpec("classification_label", "Classification Label", "text"),
    MetadataLibraryFieldSpec("classification_confidence", "Classification Confidence", "number"),
    MetadataLibraryFieldSpec("objects", "Objects", "tags"),
    MetadataLibraryFieldSpec("entities", "Entities", "tags"),
    MetadataLibraryFieldSpec("ocr_text", "OCR Text", "text"),
    MetadataLibraryFieldSpec("image_width", "Image Width", "number"),
    MetadataLibraryFieldSpec("image_height", "Image Height", "number"),
    MetadataLibraryFieldSpec("capture_datetime", "Capture Datetime", "date"),
    MetadataLibraryFieldSpec("camera_make", "Camera Make", "text"),
    MetadataLibraryFieldSpec("camera_model", "Camera Model", "text"),
    MetadataLibraryFieldSpec("gps_latitude", "GPS Latitude", "number"),
    MetadataLibraryFieldSpec("gps_longitude", "GPS Longitude", "number"),
    MetadataLibraryFieldSpec("dominant_colors", "Dominant Colors", "tags"),
    MetadataLibraryFieldSpec("analysis_model_version", "Analysis Model Version", "text"),
]
