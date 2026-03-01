from io import BytesIO

import pytest
from PIL import Image

from backend.services.image_analysis import UnsupportedImageError
from backend.services.image_analysis.extractor import load_image_and_metadata


def test_load_image_and_metadata_success():
    image = Image.new("RGB", (20, 10), color=(255, 0, 0))
    stream = BytesIO()
    image.save(stream, format="PNG")

    decoded, meta = load_image_and_metadata(stream.getvalue(), max_side=1280)
    assert decoded.size == (20, 10)
    assert meta.width == 20
    assert meta.height == 10


def test_load_image_and_metadata_invalid_bytes():
    with pytest.raises(UnsupportedImageError):
        load_image_and_metadata(b"not-an-image", max_side=1280)
