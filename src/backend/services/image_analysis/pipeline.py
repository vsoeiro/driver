"""High-level orchestration for image analysis."""

from __future__ import annotations

import time

from PIL import Image

from backend.core.config import get_settings
from backend.services.image_analysis import (
    ImageAnalysisResult,
    ImageAnalysisError,
)
from backend.services.image_analysis.classifier import classify_image
from backend.services.image_analysis.detector import YOLODetector
from backend.services.image_analysis.entities import extract_entities
from backend.services.image_analysis.extractor import load_image_and_metadata
from backend.services.image_analysis.ocr import OCRService
from backend.services.image_analysis.tagger import CLIPTagger


class ImageAnalysisPipeline:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._detector = YOLODetector(
            model_name=settings.image_analysis_yolo_model,
            device=settings.image_analysis_model_device,
        )
        self._tagger = CLIPTagger(device=settings.image_analysis_model_device)
        self._ocr = OCRService()

    @property
    def model_version(self) -> str:
        return (
            f"yolo={self._settings.image_analysis_yolo_model};"
            f"clip=ViT-B-32;ocr=rapidocr"
        )

    def analyze(self, *, image_bytes: bytes, filename: str) -> ImageAnalysisResult:
        started = time.perf_counter()
        try:
            image, technical = load_image_and_metadata(
                image_bytes,
                max_side=self._settings.image_analysis_max_infer_side,
                filename=filename,
            )

            objects = self._safe_detect(image)
            tags = self._safe_tag(image)
            ocr_text = self._safe_ocr(image)
            entities = extract_entities(ocr_text=ocr_text, filename=filename)
            category, confidence = classify_image(
                objects=objects,
                tags=tags,
                entities=entities,
                ocr_text=ocr_text,
                technical_metadata={
                    "camera_make": technical.camera_make,
                    "camera_model": technical.camera_model,
                    "image_width": technical.width,
                    "image_height": technical.height,
                },
            )

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return ImageAnalysisResult(
                status="completed",
                suggested_category=category,
                confidence=round(confidence, 4),
                objects=objects,
                entities=entities,
                tags=tags,
                technical_metadata={
                    "image_width": technical.width,
                    "image_height": technical.height,
                    "capture_datetime": technical.capture_datetime,
                    "camera_make": technical.camera_make,
                    "camera_model": technical.camera_model,
                    "gps_latitude": technical.gps_latitude,
                    "gps_longitude": technical.gps_longitude,
                    "dominant_colors": technical.dominant_colors,
                },
                ocr_text=ocr_text,
                processing_ms=elapsed_ms,
                model_version=self.model_version,
            )
        except ImageAnalysisError:
            raise
        except Exception as exc:
            raise ImageAnalysisError(str(exc)) from exc

    def _safe_detect(self, image: Image.Image) -> list[dict]:
        try:
            return self._detector.detect(image)
        except Exception:
            return []

    def _safe_tag(self, image: Image.Image) -> list[str]:
        try:
            return self._tagger.tags(image)
        except Exception:
            return []

    def _safe_ocr(self, image: Image.Image) -> str | None:
        ocr_max_side = max(int(self._settings.image_analysis_max_infer_side), 1920)
        if max(image.size) > ocr_max_side:
            resized = image.copy()
            resized.thumbnail((ocr_max_side, ocr_max_side))
            image = resized
        try:
            return self._ocr.read_text(image)
        except Exception:
            return None
