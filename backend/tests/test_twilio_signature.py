"""WhatsApp webhook signature verification.

The webhook resolves a farm from the inbound `From` number, so an unsigned
request must never reach the farm lookup or the agents.
"""
from __future__ import annotations

import pytest

from app.core import twilio_verify

URL = "https://api.example.com/api/whatsapp"
TOKEN = "test_auth_token"


def _sign(params: dict[str, str], url: str = URL, token: str = TOKEN) -> str:
    return twilio_verify.compute_signature(url, params, token)


def test_valid_signature_accepted():
    params = {"From": "whatsapp:+919876543210", "Body": "my tomato leaves are yellow"}
    assert twilio_verify.is_valid_signature(URL, params, _sign(params))


def test_missing_signature_rejected():
    assert not twilio_verify.is_valid_signature(URL, {"From": "x"}, None)
    assert not twilio_verify.is_valid_signature(URL, {"From": "x"}, "")


def test_tampered_body_rejected():
    """A signature is bound to the params - changing one invalidates it."""
    original = {"From": "whatsapp:+919876543210", "Body": "hello"}
    signature = _sign(original)
    tampered = {**original, "Body": "different"}
    assert not twilio_verify.is_valid_signature(URL, tampered, signature)


def test_spoofed_from_number_rejected():
    """The core attack: forging `From` to impersonate another farm."""
    victim = {"From": "whatsapp:+919999999999", "Body": "hello"}
    attacker_sig = _sign({"From": "whatsapp:+911111111111", "Body": "hello"})
    assert not twilio_verify.is_valid_signature(URL, victim, attacker_sig)


def test_wrong_token_rejected():
    params = {"From": "whatsapp:+919876543210", "Body": "hello"}
    assert not twilio_verify.is_valid_signature(URL, params, _sign(params, token="wrong"))


def test_wrong_url_rejected():
    params = {"Body": "hello"}
    assert not twilio_verify.is_valid_signature(
        URL, params, _sign(params, url="https://evil.example.com/api/whatsapp")
    )


def test_signature_matches_twilio_spec():
    """Known-answer test pinning our HMAC to Twilio's real algorithm.

    Both expected values were produced by the official SDK
    (`twilio.request_validator.RequestValidator.compute_signature`) and verified
    to match this implementation exactly. If this test ever fails, our signing
    has drifted from Twilio's - the webhook would start rejecting real traffic
    (or, worse, accepting forged traffic).
    """
    url = "https://mycompany.com/myapp.php?foo=1&bar=2"
    params = {
        "Digits": "1234",
        "To": "+18005551212",
        "From": "+14158675310",
        "Caller": "+14158675310",
        "CallSid": "CA1234567890ABCDE",
    }
    assert twilio_verify.compute_signature(url, params, "12345") == "GvWf1cFY/Q7PnoempGyD5oXAezc="

    # A realistic inbound WhatsApp payload.
    assert twilio_verify.compute_signature(
        "https://api.example.com/api/whatsapp",
        {"From": "whatsapp:+919876543210", "Body": "my tomato leaves are yellow", "NumMedia": "0"},
        "test_auth_token",
    ) == "xrYG7SM0zYli663CC2wSYtKQods="


def test_param_ordering_is_key_sorted():
    """Signature must not depend on dict insertion order."""
    a = {"B": "2", "A": "1"}
    b = {"A": "1", "B": "2"}
    assert _sign(a) == _sign(b)


def test_endpoint_rejects_unsigned_request(client, monkeypatch):
    monkeypatch.setattr(twilio_verify.settings, "twilio_validate_signature", True)
    resp = client.post(
        "/api/whatsapp",
        data={"From": "whatsapp:+919876543210", "Body": "hello", "NumMedia": "0"},
    )
    assert resp.status_code == 403


def test_webhook_url_override(monkeypatch):
    monkeypatch.setattr(twilio_verify.settings, "twilio_webhook_url", "https://override.example.com/api/whatsapp")
    assert twilio_verify.webhook_url("http://internal:8000/api/whatsapp") == "https://override.example.com/api/whatsapp"


def test_webhook_url_forces_https_behind_proxy(monkeypatch):
    monkeypatch.setattr(twilio_verify.settings, "twilio_webhook_url", "")
    monkeypatch.setattr(twilio_verify.settings, "twilio_force_https_webhook", True)
    assert twilio_verify.webhook_url("http://x.com/api/whatsapp") == "https://x.com/api/whatsapp"
