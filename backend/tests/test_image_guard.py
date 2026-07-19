"""Image relevance guard: diagnose only processes crop/farm photos."""
from __future__ import annotations

import pytest

from app.agents import flows


async def _stub_farm(monkeypatch):
    async def get_farm(fid):
        return {"id": fid, "language": "en"}

    async def context_blob(fid, farm=None):
        return "CTX"

    monkeypatch.setattr(flows.memory, "get_farm", get_farm)
    monkeypatch.setattr(flows.memory, "context_blob", context_blob)


@pytest.mark.asyncio
async def test_non_crop_image_is_rejected(monkeypatch):
    await _stub_farm(monkeypatch)

    async def fake_vision(*a, **k):
        return {"is_crop_image": False, "issue": None}  # e.g. a selfie

    monkeypatch.setattr(flows.fireworks, "vision", fake_vision)
    out = await flows.diagnose_image("data:image/jpeg;base64,AAAA", "f1", "")
    assert out["not_crop"] is True
    assert "crop" in out["explanation_local"].lower()
    assert not flows.needs_persisting(out), "a non-crop rejection must not record a disease"


@pytest.mark.asyncio
async def test_real_crop_image_diagnoses_normally(monkeypatch):
    await _stub_farm(monkeypatch)

    async def fake_vision(*a, **k):
        return {"is_crop_image": True, "issue": "Early Blight", "category": "disease",
                "crop_guess": "Tomato", "natural_treatment": {"remedy": "neem"}}

    monkeypatch.setattr(flows.fireworks, "vision", fake_vision)
    out = await flows.diagnose_image("data:image/jpeg;base64,AAAA", "f1", "")
    assert not out.get("not_crop")
    assert out["issue"] == "Early Blight"


@pytest.mark.asyncio
async def test_missing_flag_defaults_to_diagnosing(monkeypatch):
    """Back-compat: an older reply without is_crop_image must still diagnose."""
    await _stub_farm(monkeypatch)

    async def fake_vision(*a, **k):
        return {"issue": "Powdery Mildew", "category": "disease"}

    monkeypatch.setattr(flows.fireworks, "vision", fake_vision)
    out = await flows.diagnose_image("data:image/jpeg;base64,AAAA", "f1", "")
    assert not out.get("not_crop")
    assert out["issue"] == "Powdery Mildew"
