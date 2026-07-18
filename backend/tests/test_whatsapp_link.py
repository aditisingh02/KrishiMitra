"""WhatsApp link status + test message (P1 item 8) and alert localization (item 9)."""
from __future__ import annotations

import pytest

from app.api import routes
from app.services import notify


# ---------- phone masking ----------
def test_phone_is_masked_to_last_four():
    assert routes._mask_phone("9876543210").endswith("3210")
    assert "987654" not in routes._mask_phone("9876543210")


def test_mask_handles_short_input():
    assert routes._mask_phone("12") == "••••••"


# ---------- status endpoint ----------
def test_status_requires_auth(client):
    assert client.get("/api/whatsapp/status").status_code == 401


def test_test_send_requires_auth(client):
    assert client.post("/api/whatsapp/test").status_code == 401


# ---------- localization ----------
# WhatsApp is inbound-only now (no proactive alerts). The one outbound string
# that still exists - the link-test confirmation - is localized.
@pytest.mark.asyncio
async def test_english_skips_translation(monkeypatch):
    called = []

    async def fake_translate(strings, lang):
        called.append(1)
        return {s: s for s in strings}

    async def fake_send(to, body):
        return True

    monkeypatch.setattr(notify.i18n, "translate", fake_translate)
    monkeypatch.setattr(notify, "send_whatsapp", fake_send)

    await notify.send_test("9876543210", "en")
    assert not called, "English must not hit the translator"


@pytest.mark.asyncio
async def test_test_message_survives_translation_failure(monkeypatch):
    """Never lose the message to a translation error - fall back to English."""
    sent = {}

    async def boom(strings, lang):
        raise RuntimeError("i18n down")

    async def fake_send(to, body):
        sent["body"] = body
        return True

    monkeypatch.setattr(notify.i18n, "translate", boom)
    monkeypatch.setattr(notify, "send_whatsapp", fake_send)

    ok = await notify.send_test("9876543210", "hi")
    assert ok
    assert "linked correctly" in sent["body"]  # English fallback, still delivered


@pytest.mark.asyncio
async def test_no_proactive_alert_sender_exists():
    """Guard against the alert push being reintroduced by accident."""
    assert not hasattr(notify, "send_alert")
    assert not hasattr(notify, "localize_task")


@pytest.mark.asyncio
async def test_send_test_is_localized(monkeypatch):
    sent = {}

    async def fake_translate(strings, lang):
        return {s: f"[{lang}] {s}" for s in strings}

    async def fake_send(to, body):
        sent["body"] = body
        return True

    monkeypatch.setattr(notify.i18n, "translate", fake_translate)
    monkeypatch.setattr(notify, "send_whatsapp", fake_send)

    await notify.send_test("9876543210", "ta")
    assert "[ta]" in sent["body"]


# ---------- metrics endpoint ----------
def test_metrics_hidden_when_disabled(client, monkeypatch):
    monkeypatch.setattr(routes.settings, "metrics_enabled", False)
    assert client.get("/api/metrics").status_code == 404


def test_metrics_requires_token(client, monkeypatch):
    monkeypatch.setattr(routes.settings, "metrics_enabled", True)
    monkeypatch.setattr(routes.settings, "metrics_token", "s3cret")
    assert client.get("/api/metrics").status_code == 401
    assert client.get("/api/metrics", headers={"X-Metrics-Token": "wrong"}).status_code == 401


def test_metrics_returns_snapshot_with_token(client, monkeypatch):
    monkeypatch.setattr(routes.settings, "metrics_enabled", True)
    monkeypatch.setattr(routes.settings, "metrics_token", "s3cret")
    routes.metrics.reset()
    routes.metrics.record("crop_health", 120.0)
    r = client.get("/api/metrics", headers={"X-Metrics-Token": "s3cret"})
    assert r.status_code == 200
    assert r.json()["agents"]["crop_health"]["calls"] == 1


def test_metrics_with_empty_token_config_is_locked(client, monkeypatch):
    """Enabled but no token configured must fail closed, not open."""
    monkeypatch.setattr(routes.settings, "metrics_enabled", True)
    monkeypatch.setattr(routes.settings, "metrics_token", "")
    assert client.get("/api/metrics", headers={"X-Metrics-Token": ""}).status_code == 401
