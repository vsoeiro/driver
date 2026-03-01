"""Image decoding and technical metadata extraction."""

from __future__ import annotations

import io
from collections import Counter
from datetime import datetime

from PIL import Image, ImageOps

from backend.services.image_analysis import (
    ImageTechnicalMetadata,
    UnsupportedImageError,
)


def _parse_capture_datetime(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    # EXIF commonly stores datetime as "YYYY:MM:DD HH:MM:SS".
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_exif_map(data: bytes) -> dict:
    try:
        import exifread  # type: ignore[import-not-found]
    except Exception:
        return {}

    try:
        tags = exifread.process_file(io.BytesIO(data), details=False)
    except Exception:
        return {}
    return dict(tags or {})


def _parse_gps_coord(value: str) -> float | None:
    # Expected shape: [deg, min, sec]
    raw = value.strip().strip("[]")
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != 3:
        return None

    def _to_float(part: str) -> float:
        if "/" in part:
            left, right = part.split("/", 1)
            return float(left) / float(right)
        return float(part)

    try:
        degrees = _to_float(parts[0])
        minutes = _to_float(parts[1])
        seconds = _to_float(parts[2])
    except Exception:
        return None

    return degrees + (minutes / 60.0) + (seconds / 3600.0)


def _dominant_colors(image: Image.Image, limit: int = 5) -> list[str]:
    sample = image.convert("RGB")
    sample.thumbnail((128, 128))
    pixels = list(sample.getdata())
    if not pixels:
        return []
    counter = Counter(pixels)
    ordered = [rgb for rgb, _count in counter.most_common(limit)]
    return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in ordered]


def _looks_like_screenshot(*, filename: str | None, width: int, height: int, camera_make: str | None, camera_model: str | None) -> bool:
    if camera_make or camera_model:
        return False
    name = str(filename or "").lower()
    if any(token in name for token in ("screenshot", "screen shot", "captura de tela", "print", "scrn")):
        return True
    # Common device screenshot aspect ratios.
    if width > 0 and height > 0:
        ratio = max(width, height) / max(1, min(width, height))
        return 1.6 <= ratio <= 2.4
    return False


def load_image_and_metadata(data: bytes, *, max_side: int, filename: str | None = None) -> tuple[Image.Image, ImageTechnicalMetadata]:
    try:
        image = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedImageError(f"Unsupported or invalid image bytes: {exc}") from exc

    try:
        image = ImageOps.exif_transpose(image)
        image.load()
    except Exception as exc:
        raise UnsupportedImageError(f"Failed to decode image payload: {exc}") from exc

    width, height = image.size
    if width <= 0 or height <= 0:
        raise UnsupportedImageError("Decoded image has invalid dimensions")

    exif = _extract_exif_map(data)
    capture_datetime = _parse_capture_datetime(exif.get("EXIF DateTimeOriginal"))
    camera_make = str(exif.get("Image Make") or "").strip() or None
    camera_model = str(exif.get("Image Model") or "").strip() or None
    if _looks_like_screenshot(
        filename=filename,
        width=width,
        height=height,
        camera_make=camera_make,
        camera_model=camera_model,
    ):
        camera_make = camera_make or "system"
        camera_model = camera_model or "screenshot"

    gps_lat = None
    gps_lon = None
    if "GPS GPSLatitude" in exif and "GPS GPSLongitude" in exif:
        gps_lat = _parse_gps_coord(str(exif.get("GPS GPSLatitude")))
        gps_lon = _parse_gps_coord(str(exif.get("GPS GPSLongitude")))
        lat_ref = str(exif.get("GPS GPSLatitudeRef") or "").upper()
        lon_ref = str(exif.get("GPS GPSLongitudeRef") or "").upper()
        if gps_lat is not None and lat_ref == "S":
            gps_lat = -gps_lat
        if gps_lon is not None and lon_ref == "W":
            gps_lon = -gps_lon

    metadata = ImageTechnicalMetadata(
        width=width,
        height=height,
        capture_datetime=capture_datetime,
        camera_make=camera_make,
        camera_model=camera_model,
        gps_latitude=gps_lat,
        gps_longitude=gps_lon,
        dominant_colors=_dominant_colors(image),
    )

    if max(width, height) > max_side:
        resized = image.copy()
        resized.thumbnail((max_side, max_side))
        image = resized

    return image, metadata
