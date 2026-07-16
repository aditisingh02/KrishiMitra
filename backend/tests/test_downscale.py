"""Server-side image downscaling.

Covers the WhatsApp/direct-API path, where no browser pre-shrinks the photo.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core import uploads
from app.core.uploads import _downscale_sync, downscale_image


def _jpeg(w: int, h: int, color=(34, 139, 34)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _size(raw: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(raw)) as im:
        return im.size


def test_large_image_downscaled_to_max_edge():
    raw = _jpeg(4000, 3000)
    out, mime = _downscale_sync(raw, "image/jpeg")
    assert max(_size(out)) == 1280
    assert mime == "image/jpeg"
    assert len(out) < len(raw)


def test_aspect_ratio_preserved():
    out, _ = _downscale_sync(_jpeg(4000, 2000), "image/jpeg")
    w, h = _size(out)
    assert (w, h) == (1280, 640)


def test_portrait_uses_long_edge():
    out, _ = _downscale_sync(_jpeg(2000, 4000), "image/jpeg")
    assert _size(out) == (640, 1280)


def test_small_image_untouched_idempotent():
    """A browser-downscaled photo must not be re-encoded (generation loss)."""
    raw = _jpeg(1000, 800)
    out, mime = _downscale_sync(raw, "image/jpeg")
    assert out is raw
    assert mime == "image/jpeg"


def test_image_at_limit_untouched():
    raw = _jpeg(1280, 900)
    out, _ = _downscale_sync(raw, "image/jpeg")
    assert out is raw


def test_downscale_is_idempotent():
    """Running twice must equal running once - no progressive quality decay."""
    once, _ = _downscale_sync(_jpeg(4000, 3000), "image/jpeg")
    twice, _ = _downscale_sync(once, "image/jpeg")
    assert twice is once


def test_png_with_alpha_converted_to_jpeg():
    buf = io.BytesIO()
    Image.new("RGBA", (3000, 2000), (0, 128, 0, 255)).save(buf, format="PNG")
    out, mime = _downscale_sync(buf.getvalue(), "image/png")
    assert mime == "image/jpeg"
    assert max(_size(out)) == 1280


def test_undecodable_bytes_fall_through():
    """A resize failure must never cost the farmer a diagnosis."""
    junk = b"this is not an image"
    out, mime = _downscale_sync(junk, "image/jpeg")
    assert out == junk
    assert mime == "image/jpeg"


def test_respects_configured_edge(monkeypatch):
    monkeypatch.setattr(uploads.settings, "max_image_edge", 512)
    out, _ = _downscale_sync(_jpeg(2000, 1000), "image/jpeg")
    assert max(_size(out)) == 512


def test_exif_orientation_is_applied():
    """A sideways phone photo must come out upright, not silently rotated."""
    buf = io.BytesIO()
    img = Image.new("RGB", (4000, 2000), (10, 90, 10))
    exif = img.getexif()
    exif[274] = 6  # Orientation: rotate 90° CW
    img.save(buf, format="JPEG", exif=exif)

    out, _ = _downscale_sync(buf.getvalue(), "image/jpeg")
    # 4000x2000 rotated becomes portrait 2000x4000 -> long edge is height.
    w, h = _size(out)
    assert h > w, "EXIF orientation was dropped - image came out sideways"


@pytest.mark.asyncio
async def test_async_wrapper_matches_sync():
    raw = _jpeg(2000, 1500)
    out, mime = await downscale_image(raw, "image/jpeg")
    assert max(_size(out)) == 1280
    assert mime == "image/jpeg"
