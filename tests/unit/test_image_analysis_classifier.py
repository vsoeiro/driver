from backend.services.image_analysis.classifier import classify_image


def test_classifier_returns_document_when_tags_match():
    category, confidence = classify_image(
        objects=[],
        tags=["document", "invoice"],
        entities=[],
        ocr_text=None,
    )
    assert category == "document"
    assert confidence >= 0.8


def test_classifier_returns_generic_for_low_signal():
    category, confidence = classify_image(
        objects=[],
        tags=[],
        entities=[],
        ocr_text=None,
    )
    assert category == "generic"
    assert confidence < 0.72
