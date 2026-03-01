"""Rule-based classifier for image categories."""

from __future__ import annotations


def classify_image(
    *,
    objects: list[dict],
    tags: list[str],
    entities: list[str],
    ocr_text: str | None,
    technical_metadata: dict | None = None,
) -> tuple[str, float]:
    object_labels = {str(obj.get("label", "")).lower() for obj in objects}
    tag_set = {str(tag).lower() for tag in tags}
    entity_set = {str(entity).lower() for entity in entities}
    ocr_lower = (ocr_text or "").lower()
    technical_metadata = technical_metadata or {}
    camera_model = str(technical_metadata.get("camera_model") or "").lower()

    if "screenshot" in camera_model:
        if any(key in ocr_lower for key in ("invoice", "receipt", "cnpj", "cpf", "pix", "total")):
            return "document", 0.86
        if any(key in ocr_lower for key in ("http", "@", "www", "login", "settings", "menu", "notification")):
            return "screenshot", 0.88
        return "screenshot", 0.8

    if any(key in ocr_lower for key in ("manga", "comic", "chapter", "issue", "vol.", "volume", "dialogue")):
        return "comic_page", 0.84

    if {"invoice", "receipt"} & tag_set or "document" in tag_set:
        return "document", 0.85
    if any(key in ocr_lower for key in ("invoice", "total", "cnpj", "cpf")):
        return "document", 0.8
    if {"person", "face"} & object_labels or {"person", "face"} & tag_set:
        return "portrait", 0.82
    if {"animal"} & tag_set:
        return "animal", 0.78
    if {"vehicle"} & tag_set or {"car", "bus", "truck", "motorcycle"} & object_labels:
        return "vehicle", 0.78
    if {"city", "building", "outdoor"} & tag_set:
        return "urban", 0.72
    if {"nature"} & tag_set:
        return "nature", 0.72
    if entity_set:
        return "entity_rich", 0.66
    return "generic", 0.55
