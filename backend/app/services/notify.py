"""Twilio WhatsApp messaging (outbound). Uses the REST API directly via httpx
so no extra SDK dependency. No-ops gracefully if Twilio isn't configured."""
from __future__ import annotations

import logging

import httpx

from app.core import http
from app.core.config import settings
from app.services import i18n

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
        r = await http.get_client().post(
            url,
            data=data,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=20,
        )
        if r.status_code >= 300:
            logger.warning("Twilio send failed %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except httpx.HTTPError as e:
        logger.warning("Twilio send error: %s", e)
        return False


# ---- farmer-facing message templates ----
# WhatsApp is inbound-only (consult + diagnose). The only outbound messages are
# direct replies to what a farmer sent, plus this one-off link test. No proactive
# alerts are pushed. The farmer reads these in their messaging app, so localize.
TEST_MESSAGE = (
    "This is a test message from KrishiMitra. Your WhatsApp is linked correctly - "
    "you can now send a crop photo or ask a question here any time."
)


async def _localize(text: str, lang: str | None) -> str:
    """Translate a message into the farmer's language (English passes through)."""
    if not lang or lang == "en":
        return text
    try:
        return (await i18n.translate([text], lang)).get(text, text)
    except Exception as e:  # noqa: BLE001 - never lose the message to a translation failure
        logger.warning("message localization failed (%s): %s", lang, e)
        return text


async def localize_text(text: str, lang: str | None) -> str:
    """Public: localize a single message string (cached via i18n)."""
    return await _localize(text, lang)


async def send_test(phone: str, lang: str | None) -> bool:
    """Send the 'your WhatsApp is linked' confirmation."""
    return await send_whatsapp(phone, f"🌱 {await _localize(TEST_MESSAGE, lang)}")
