"""Object detection wrapper using YOLO."""

from __future__ import annotations

from typing import Any

from PIL import Image


class YOLODetector:
    def __init__(self, *, model_name: str, device: str) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        from ultralytics import YOLO  # type: ignore[import-not-found]

        self._model = YOLO(self._model_name)
        return self._model

    def detect(self, image: Image.Image, *, max_items: int = 10) -> list[dict[str, Any]]:
        model = self._ensure_model()
        results = model.predict(image, verbose=False, device=self._device)
        objects: list[dict[str, Any]] = []
        if not results:
            return objects

        result = results[0]
        boxes = getattr(result, "boxes", None)
        names = getattr(result, "names", {}) or {}
        if boxes is None:
            return objects

        for idx in range(len(boxes)):
            if len(objects) >= max_items:
                break
            box = boxes[idx]
            cls_idx = int(box.cls[0].item()) if getattr(box, "cls", None) is not None else -1
            confidence = (
                float(box.conf[0].item())
                if getattr(box, "conf", None) is not None
                else 0.0
            )
            label = str(names.get(cls_idx, f"class_{cls_idx}"))
            objects.append(
                {
                    "label": label,
                    "confidence": round(confidence, 4),
                }
            )
        return objects
