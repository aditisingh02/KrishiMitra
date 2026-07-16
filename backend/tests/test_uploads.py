"""Upload size + MIME validation."""
from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

from app.core import uploads
from app.core.uploads import read_image_data_url, read_image_upload


def _upload(data: bytes, content_type: str = "image/jpeg") -> UploadFile:
    return UploadFile(
        filename="leaf.jpg",
        file=io.BytesIO(data),
        headers={"content-type": content_type},
    )


@pytest.mark.asyncio
async def test_valid_image_accepted():
    raw, mime = await read_image_upload(_upload(b"\xff\xd8\xff fake jpeg"))
    assert mime == "image/jpeg"
    assert raw.startswith(b"\xff\xd8\xff")


@pytest.mark.asyncio
@pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/webp"])
async def test_allowed_types(mime):
    _, got = await read_image_upload(_upload(b"data", mime))
    assert got == mime


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mime", ["application/pdf", "text/html", "application/zip", "image/svg+xml", ""]
)
async def test_disallowed_types_rejected(mime):
    with pytest.raises(HTTPException) as e:
        await read_image_upload(_upload(b"data", mime))
    assert e.value.status_code == 415


@pytest.mark.asyncio
async def test_content_type_params_are_stripped():
    _, mime = await read_image_upload(_upload(b"x", "image/jpeg; charset=binary"))
    assert mime == "image/jpeg"


@pytest.mark.asyncio
async def test_oversized_upload_rejected(monkeypatch):
    monkeypatch.setattr(uploads.settings, "max_upload_bytes", 1024)
    with pytest.raises(HTTPException) as e:
        await read_image_upload(_upload(b"x" * 2048))
    assert e.value.status_code == 413
    assert "too large" in e.value.detail.lower()


@pytest.mark.asyncio
async def test_upload_at_limit_accepted(monkeypatch):
    monkeypatch.setattr(uploads.settings, "max_upload_bytes", 1024)
    raw, _ = await read_image_upload(_upload(b"x" * 1024))
    assert len(raw) == 1024


@pytest.mark.asyncio
async def test_empty_upload_rejected():
    with pytest.raises(HTTPException) as e:
        await read_image_upload(_upload(b""))
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_data_url_format():
    url = await read_image_data_url(_upload(b"abc", "image/png"))
    assert url.startswith("data:image/png;base64,")
