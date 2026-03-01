"""Lightweight entity extraction from OCR/name context."""

from __future__ import annotations

import re

ENTITY_PATTERNS: dict[str, str] = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "url": r"https?://[^\s]+",
    "cpf": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "cnpj": r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
    "date": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    "phone": r"\b(?:\+?\d{1,3}\s?)?(?:\(?\d{2,3}\)?\s?)?\d{4,5}[-\s]?\d{4}\b",
    "hashtag": r"#[A-Za-z0-9_]{2,}",
    "mention": r"@[A-Za-z0-9_]{2,}",
}


def extract_entities(*, ocr_text: str | None, filename: str) -> list[str]:
    text = f"{filename} {ocr_text or ''}".strip()
    if not text:
        return []

    found: set[str] = set()
    for label, pattern in ENTITY_PATTERNS.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.add(label)

    # Filename semantic hints.
    filename_tokens = re.findall(r"[A-Za-z]{4,}", filename.lower())
    stopwords = {
        "image", "img", "photo", "file", "final", "copy", "edited",
        "screenshot", "screen", "shot", "capture",
    }
    for token in filename_tokens[:12]:
        if token in stopwords:
            continue
        found.add(token)

    # OCR lexical hints.
    ocr_tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{3,}\b", (ocr_text or "").lower())
    freq: dict[str, int] = {}
    for token in ocr_tokens:
        if token in stopwords:
            continue
        if token.isdigit():
            continue
        freq[token] = freq.get(token, 0) + 1
    for token, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:12]:
        found.add(token)

    return sorted(found)
