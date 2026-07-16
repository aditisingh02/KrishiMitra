"""Accuracy gate for image downscaling. OPT-IN — not part of the default suite.

Downscaling is the one latency change that touches what the vision model actually
sees, so it gets verified rather than assumed. This runs real diagnoses against
labeled PlantVillage photos at several resolutions and compares accuracy.

    RUN_VISION_EVAL=1 pytest tests/test_downscale_accuracy.py -s

Excluded from the default run because it costs real Fireworks calls and needs a
network fetch. The gate: **accuracy at 1280 must match native**. If it doesn't,
raise `settings.max_image_edge` (1568) rather than ship the regression — never
trade a correct diagnosis for latency.

Images are cached under tests/fixtures/images/ and are gitignored; nothing is
committed to the repo.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_VISION_EVAL"),
    reason="opt-in: costs real vision API calls (set RUN_VISION_EVAL=1)",
)

FIXTURES = Path(__file__).parent / "fixtures"
IMAGES = FIXTURES / "images"
MANIFEST = FIXTURES / "plantvillage.json"

# Resolutions to compare. `None` = native (the control).
RESOLUTIONS: list[int | None] = [None, 1280, 1024]


def _load_manifest() -> list[dict]:
    """Labeled samples: [{"file": "...", "url": "...", "issue": "...", "category": "..."}]."""
    if not MANIFEST.exists():
        pytest.skip(f"No manifest at {MANIFEST} - see the module docstring")
    return json.loads(MANIFEST.read_text())


def _ensure_image(entry: dict) -> Path:
    IMAGES.mkdir(parents=True, exist_ok=True)
    path = IMAGES / entry["file"]
    if not path.exists():
        urllib.request.urlretrieve(entry["url"], path)  # noqa: S310 - manifest is ours
    return path


def _resized(raw: bytes, edge: int | None) -> bytes:
    if edge is None:
        return raw
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((edge, edge), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue()


async def _diagnose(raw: bytes) -> dict:
    """Vision-only call - no DB, so this runs without Postgres."""
    import base64

    from app.agents import prompts
    from app.core.config import settings
    from app.core.fireworks import fireworks

    data_url = f"data:image/jpeg;base64,{base64.b64encode(raw).decode()}"
    return await fireworks.vision(
        "Analyze this crop photo and respond in the required JSON schema.",
        data_url,
        system=prompts.VISION_DIAGNOSIS,
        model=settings.model_vision,
    )


def _matches(result: dict, entry: dict) -> bool:
    """Lenient substring match - the model phrases issues freely ('Early Blight
    (Alternaria)' vs 'Early Blight'). We're measuring resolution sensitivity, not
    exact wording."""
    issue = (result.get("issue") or "").lower()
    return bool(issue) and entry["issue"].lower() in issue


def test_downscaling_does_not_reduce_accuracy():
    entries = _load_manifest()
    scores: dict[str, int] = {}
    latency: dict[str, float] = {}

    async def run() -> None:
        from app.core.fireworks import fireworks

        await fireworks.startup()
        try:
            for edge in RESOLUTIONS:
                label = "native" if edge is None else str(edge)
                hits = 0
                started = asyncio.get_event_loop().time()
                for entry in entries:
                    raw = _ensure_image(entry).read_bytes()
                    result = await _diagnose(_resized(raw, edge))
                    hits += _matches(result, entry)
                scores[label] = hits
                latency[label] = (asyncio.get_event_loop().time() - started) / len(entries)
        finally:
            await fireworks.aclose()

    asyncio.run(run())

    n = len(entries)
    print(f"\n{'resolution':<12}{'accuracy':<14}{'avg latency':<12}")
    for label in (("native" if e is None else str(e)) for e in RESOLUTIONS):
        print(f"{label:<12}{scores[label]}/{n} ({scores[label]/n:.0%}){'':<3}{latency[label]:.1f}s")

    # The gate: 1280 must not lose accuracy vs native.
    assert scores["1280"] >= scores["native"], (
        f"1280px lost accuracy vs native ({scores['1280']}/{n} vs {scores['native']}/{n}). "
        "Raise settings.max_image_edge to 1568 rather than shipping this."
    )
