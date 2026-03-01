"""Semantic image tagging with CLIP."""

from __future__ import annotations

from typing import Sequence

import torch
from PIL import Image

DEFAULT_TAG_CANDIDATES: tuple[str, ...] = (
    "person",
    "face",
    "document",
    "screenshot",
    "invoice",
    "receipt",
    "nature",
    "animal",
    "food",
    "vehicle",
    "outdoor",
    "indoor",
    "city",
    "building",
    "product",
    "logo",
)


class CLIPTagger:
    def __init__(self, *, device: str) -> None:
        self._device = device
        self._model = None
        self._preprocess = None
        self._tokenizer = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model, self._preprocess, self._tokenizer
        import open_clip  # type: ignore[import-not-found]

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32",
            pretrained="laion2b_s34b_b79k",
            device=self._device,
        )
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = tokenizer
        return self._model, self._preprocess, self._tokenizer

    def tags(
        self,
        image: Image.Image,
        *,
        candidates: Sequence[str] = DEFAULT_TAG_CANDIDATES,
        threshold: float = 0.18,
        limit: int = 6,
    ) -> list[str]:
        model, preprocess, tokenizer = self._ensure_model()
        if not candidates:
            return []

        image_tensor = preprocess(image).unsqueeze(0).to(self._device)
        text_tensor = tokenizer(list(candidates)).to(self._device)

        with torch.no_grad():
            image_features = model.encode_image(image_tensor)
            text_features = model.encode_text(text_tensor)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            text_features /= text_features.norm(dim=-1, keepdim=True)
            similarities = (100.0 * image_features @ text_features.T).softmax(dim=-1)

        scores = similarities[0].tolist()
        ranked = sorted(zip(candidates, scores), key=lambda item: item[1], reverse=True)
        selected = [label for label, score in ranked if float(score) >= threshold][:limit]
        return selected
