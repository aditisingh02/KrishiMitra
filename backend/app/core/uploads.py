"""Upload validation and downscaling.

`UploadFile.read()` pulls the whole file into memory and we then base64 it into a
data URL for the vision model - so an unbounded upload is both an OOM risk and a
large, silent token bill. Every image entering the system goes through
`read_image_upload`, which enforces a size ceiling and a MIME allowlist, then
downscales.

**Why downscale here as well as in the browser?** The web client already resizes
before upload (frontend/lib/image.ts), which is where the real latency win is. But
this path also serves images the browser never touched: WhatsApp photos fetched
server-side from Twilio, and any direct API caller. This is the backstop, and it
keeps the vision model's image-token cost bounded regardless of who called us.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from app.core.config import settings

logger = logging.getLogger("krishimitra.uploads")

_CHUNK = 64 * 1024


def _human(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB"


async def read_image_upload(file: UploadFile) -> tuple[bytes, str]:
    """Read + validate an uploaded image. Returns (raw_bytes, mime).

    Raises 415 for a disallowed type and 413 once the stream exceeds
    `max_upload_bytes` - streamed in chunks so an oversized file is rejected
    without ever being fully buffered.
    """
    mime = (file.content_type or "").split(";")[0].strip().lower()
    allowed = settings.allowed_image_type_set
    if mime not in allowed:
        raise HTTPException(
            415,
            f"Unsupported image type '{mime or 'unknown'}'. Allowed: {', '.join(sorted(allowed))}",
        )

    limit = settings.max_upload_bytes
    buf = bytearray()
    while chunk := await file.read(_CHUNK):
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(413, f"Image too large - maximum is {_human(limit)}")

    if not buf:
        raise HTTPException(400, "Empty image")
    return bytes(buf), mime


def _downscale_sync(raw: bytes, mime: str) -> tuple[bytes, str]:
    """Downscale to `max_image_edge` on the long side. Pure/blocking - call via to_thread.

    Idempotent: an image already within the limit is returned untouched rather
    than re-encoded, so a browser-downscaled photo doesn't take a second
    generation-loss hit.

    Never raises: an undecodable image falls through to the original bytes and
    lets the vision model decide. Losing a diagnosis to a resize failure would be
    a worse outcome than sending a big image.
    """
    limit = settings.max_image_edge
    try:
        with Image.open(io.BytesIO(raw)) as img:
            # Bake in EXIF rotation - phone photos are usually stored sideways
            # with an orientation flag, and re-encoding would silently drop it.
            img = ImageOps.exif_transpose(img)
            if max(img.size) <= limit:
                return raw, mime

            before = img.size
            img.thumbnail((limit, limit), Image.LANCZOS)  # preserves aspect ratio
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")  # JPEG can't hold alpha/palette

            out = io.BytesIO()
            img.save(out, format="JPEG", quality=settings.image_jpeg_quality, optimize=True)
            data = out.getvalue()

        if len(data) >= len(raw):
            return raw, mime  # re-encode didn't help - keep the original
        logger.info(
            "downscaled image %sx%s -> %sx%s | %.0fKB -> %.0fKB",
            before[0], before[1], img.size[0], img.size[1], len(raw) / 1024, len(data) / 1024,
        )
        return data, "image/jpeg"
    except Exception as e:  # noqa: BLE001
        logger.warning("image downscale failed (%s) - sending original", e)
        return raw, mime


async def downscale_image(raw: bytes, mime: str) -> tuple[bytes, str]:
    """Downscale off the event loop - Pillow is CPU-bound (~200-400ms on 12MP)."""
    return await asyncio.to_thread(_downscale_sync, raw, mime)


async def read_image_data_url(file: UploadFile) -> str:
    """Validated + downscaled upload -> `data:<mime>;base64,...` for the vision model."""
    raw, mime = await read_image_upload(file)
    raw, mime = await downscale_image(raw, mime)
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
