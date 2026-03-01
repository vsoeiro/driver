"""OCR wrapper for image analysis."""

from __future__ import annotations

import re

from PIL import Image


class OCRService:
    def __init__(self) -> None:
        self._engine = None

    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

        self._engine = RapidOCR()
        return self._engine

    @staticmethod
    def _cleanup(text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        return normalized[:8000]

    @staticmethod
    def _extract_text(output) -> str:
        if not output:
            return ""
        chunks: list[str] = []
        for line in output:
            try:
                # rapidocr common shape: [box, text, score]
                text = str(line[1]) if len(line) >= 2 else ""
                score = float(line[2]) if len(line) >= 3 else 1.0
                if text and score >= 0.35:
                    chunks.append(text)
            except Exception:
                continue
        return " ".join(chunks).strip()

    @staticmethod
    def _variants(image: Image.Image) -> list[Image.Image]:
        variants: list[Image.Image] = [image]
        gray = image.convert("L")
        variants.append(gray)

        # Improve contrast for comic balloons / low contrast captions.
        try:
            from PIL import ImageOps

            autocontrast = ImageOps.autocontrast(gray)
            variants.append(autocontrast)

            # Binarized version improves OCR in many scans.
            bw = autocontrast.point(lambda p: 255 if p > 170 else 0, mode="1").convert("L")
            variants.append(bw)
        except Exception:
            pass

        # Upscale smaller images to improve OCR recall.
        w, h = image.size
        if max(w, h) < 1400:
            try:
                upscale = image.resize((int(w * 1.8), int(h * 1.8)), Image.Resampling.LANCZOS)
                variants.append(upscale)
            except Exception:
                pass

        # Tiled crops help when text is small (e.g. comics/pages with speech balloons).
        if w >= 900 and h >= 900:
            try:
                step_x = w // 2
                step_y = h // 2
                for i in range(2):
                    for j in range(2):
                        left = i * step_x
                        upper = j * step_y
                        right = min(w, left + step_x)
                        lower = min(h, upper + step_y)
                        crop = image.crop((left, upper, right, lower))
                        variants.append(crop)
            except Exception:
                pass

        return variants

    def read_text(self, image: Image.Image) -> str | None:
        engine = self._ensure_engine()
        best = ""
        for variant in self._variants(image):
            try:
                output, _ = engine(variant)
            except Exception:
                continue
            text = self._extract_text(output)
            if len(text) > len(best):
                best = text
        cleaned = self._cleanup(best)
        return cleaned or None
