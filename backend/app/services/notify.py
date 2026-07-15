"""Twilio WhatsApp messaging (outbound). Uses the REST API directly via httpx
so no extra SDK dependency. No-ops gracefully if Twilio isn't configured."""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("krishimitra.notify")


def configured() -> bool:
    return bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_whatsapp_from
    )


def _to_whatsapp(number: str) -> str:
    number = number.strip()
    if number.startswith("whatsapp:"):
        return number
    if not number.startswith("+"):
        # assume India if no country code
        digits = "".join(ch for ch in number if ch.isdigit())
        number = "+91" + digits[-10:] if len(digits) >= 10 else "+" + digits
    return f"whatsapp:{number}"


async def send_whatsapp(to_number: str, body: str) -> bool:
    """Send a WhatsApp message. Returns True on success, False otherwise."""
    if not configured():
        logger.info("Twilio not configured - skipping WhatsApp to %s", to_number)
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    data = {
        "From": settings.twilio_whatsapp_from,
        "To": _to_whatsapp(to_number),
        "Body": body[:1500],
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                url, data=data, auth=(settings.twilio_account_sid, settings.twilio_auth_token)
            )
        if r.status_code >= 300:
            logger.warning("Twilio send failed %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except httpx.HTTPError as e:
        logger.warning("Twilio send error: %s", e)
        return False
