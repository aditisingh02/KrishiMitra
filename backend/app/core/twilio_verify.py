"""Twilio request signature validation.

The WhatsApp webhook is a public, unauthenticated endpoint that resolves a farm
from the inbound `From` number. Without signature validation anyone who finds the
URL can forge a request, impersonate any farm by its phone number, read that
farm's AI advice and burn credits. Twilio signs every request; we recompute the
signature and reject mismatches.

Algorithm (per Twilio's spec): take the full request URL, append each POST param
sorted by key as `key + value`, HMAC-SHA1 with the auth token, base64 the digest,
and compare against the `X-Twilio-Signature` header in constant time.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from app.core.config import settings

logger = logging.getLogger("krishimitra.twilio")


def compute_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Return the expected X-Twilio-Signature for a request."""
    payload = url
    for key in sorted(params):
        payload += key + (params[key] or "")
    digest = hmac.new(
        auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def is_valid_signature(url: str, params: dict[str, str], signature: str | None) -> bool:
    """Constant-time check of an inbound Twilio signature."""
    if not signature:
        return False
    token = settings.twilio_auth_token
    if not token:
        logger.error("TWILIO_AUTH_TOKEN not set - cannot verify webhook signature")
        return False
    expected = compute_signature(url, params, token)
    return hmac.compare_digest(expected, signature)


def webhook_url(request_url: str) -> str:
    """The URL Twilio signed.

    Twilio signs the public URL it was configured with. Behind a proxy (Render,
    ngrok) the app may see `http://` internally while Twilio signed `https://`,
    which would break validation - so allow an explicit override.
    """
    override = settings.twilio_webhook_url
    if override:
        return override
    # Trust the forwarded scheme when terminating TLS at a proxy.
    if request_url.startswith("http://") and settings.twilio_force_https_webhook:
        return "https://" + request_url[len("http://") :]
    return request_url
