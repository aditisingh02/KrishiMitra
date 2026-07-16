"""Upload validation.

`UploadFile.read()` pulls the whole file into memory and we then base64 it into a
data URL for the vision model - so an unbounded upload is both an OOM risk and a
large, silent token bill. Every image entering the system goes through
`read_image_upload`, which enforces a size ceiling and a MIME allowlist.
"""
from __future__ import annotations

import base64

from fastapi import HTTPException, UploadFile

from app.core.config import settings

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


async def read_image_data_url(file: UploadFile) -> str:
    """Validated upload -> `data:<mime>;base64,...` URL for the vision model."""
    raw, mime = await read_image_upload(file)
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
