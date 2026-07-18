"""Async WhatsApp image diagnosis: ack now, push the result later.

Vision diagnosis (~30s) exceeds Twilio's webhook window (~15s). Doing it inline
times the webhook out and the farmer gets nothing. The webhook must ack instantly
and push the diagnosis as a separate message when it's ready.
"""
from __future__ import annotations

import pytest

from app.api import routes
from app.api.routes import _diagnose_and_push


# ---------- background pusher ----------
@pytest.fixture
def _push(monkeypatch):
    sent: list[str] = []

    class FakeResp:
        content = b"\xff\xd8\xff fake jpeg bytes"
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, *a, **k):
            return FakeResp()

    async def send(to, body):
        sent.append(body)
        return True

    async def downscale(raw, mime):
        return raw, "image/jpeg"

    monkeypatch.setattr(routes.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(routes.notify, "send_whatsapp", send)
    monkeypatch.setattr(routes.notify, "localize_text", lambda t, l: _ident(t))
    monkeypatch.setattr(routes, "downscale_image", downscale)
    return sent


def _ident(t):
    async def inner():
        return t
    return inner()


@pytest.mark.asyncio
async def test_diagnosis_is_pushed_when_ready(monkeypatch, _push):
    async def diagnose(data_url, farm_id, note):
        return {"issue": "Powdery Mildew", "severity": "medium", "confidence": 0.9,
                "natural_treatment": {"remedy": "Raw milk spray 1:9"}}

    async def persist(diag, farm_id):
        pass

    monkeypatch.setattr(routes.flows, "diagnose_image", diagnose)
    monkeypatch.setattr(routes.flows, "needs_persisting", lambda d: True)
    monkeypatch.setattr(routes.flows, "persist_diagnosis", persist)

    await _diagnose_and_push("f1", "whatsapp:+919324341202", "http://media/x.jpg", "image/jpeg", "", "en")
    assert _push, "no message was pushed"
    assert "Powdery Mildew" in _push[0]


@pytest.mark.asyncio
async def test_oversized_photo_pushes_a_clear_message(monkeypatch, _push):
    monkeypatch.setattr(routes.settings, "max_upload_bytes", 4)  # smaller than the fake bytes
    await _diagnose_and_push("f1", "whatsapp:+919324341202", "http://media/x.jpg", "image/jpeg", "", "en")
    assert any("too large" in m for m in _push)


@pytest.mark.asyncio
async def test_diagnosis_failure_pushes_apology_not_silence(monkeypatch, _push):
    async def boom(*a, **k):
        raise RuntimeError("vision down")

    monkeypatch.setattr(routes.flows, "diagnose_image", boom)
    await _diagnose_and_push("f1", "whatsapp:+919324341202", "http://media/x.jpg", "image/jpeg", "", "en")
    assert any("couldn't read that photo" in m.lower() or "could not read" in m.lower() for m in _push), _push


# ---------- webhook acks without doing the slow work ----------
@pytest.mark.asyncio
async def test_image_webhook_acks_and_schedules_background(monkeypatch):
    """The webhook must return immediately and hand diagnosis to a background task,
    never call diagnose_image inline."""
    from starlette.background import BackgroundTasks

    async def profile_by_phone(p):
        return {"id": "u1", "active_farm_id": "f1", "language": "en", "phone": "9324341202"}

    async def farm_exists(fid):
        return True

    async def get_farm(fid):
        return {"id": "f1", "language": "en"}

    monkeypatch.setattr(routes.memory, "profile_by_phone", profile_by_phone)
    monkeypatch.setattr(routes.memory, "farm_exists", farm_exists)
    monkeypatch.setattr(routes.memory, "get_farm", get_farm)
    monkeypatch.setattr(routes.settings, "twilio_validate_signature", False)
    monkeypatch.setattr(routes.notify, "localize_text", lambda t, l: _ident(t))

    called = {"diagnose": False}
    async def diagnose(*a, **k):
        called["diagnose"] = True
        return {}
    monkeypatch.setattr(routes.flows, "diagnose_image", diagnose)

    class FakeForm(dict):
        pass
    form = FakeForm({"From": "whatsapp:+919324341202", "NumMedia": "1",
                     "MediaUrl0": "http://media/x.jpg", "MediaContentType0": "image/jpeg", "Body": ""})

    class FakeReq:
        url = "https://x/api/whatsapp"
        headers: dict = {}
        client = type("C", (), {"host": "1.2.3.4"})()
        async def form(self):
            return form

    bg = BackgroundTasks()
    resp = await routes.whatsapp_inbound(FakeReq(), bg)

    assert resp.status_code == 200
    assert b"analysing" in resp.body.lower() or b"analyzing" in resp.body.lower()
    assert not called["diagnose"], "diagnosis must NOT run inline in the webhook"
    assert any(t.func is routes._diagnose_and_push for t in bg.tasks), "background push not scheduled"
