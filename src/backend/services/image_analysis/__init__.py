"""Image analysis pipeline primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ImageAnalysisError(Exception):
    """Base error for analysis failures."""


class UnsupportedImageError(ImageAnalysisError):
    """Raised when image cannot be decoded or format is unsupported."""


@dataclass(slots=True)
class ImageTechnicalMetadata:
    width: int
    height: int
    capture_datetime: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    dominant_colors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImageAnalysisResult:
    status: str
    suggested_category: str
    confidence: float
    objects: list[dict[str, Any]] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    technical_metadata: dict[str, Any] = field(default_factory=dict)
    ocr_text: str | None = None
    processing_ms: int | None = None
    model_version: str = "unknown"
    error: str | None = None


SUPPORTED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "gif",
    "bmp",
    "tiff",
    "tif",
    "heic",
    "avif",
}
