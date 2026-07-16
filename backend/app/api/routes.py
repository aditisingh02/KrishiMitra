"""HTTP API for KrishiMitra. All farm routes require a Clerk-authenticated user;
the farm is keyed by the Clerk user id."""
from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.agents import flows, orchestrator
from app.core import guards, languages, twilio_verify
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.limits import ip_rate_limit, user_rate_limit
from app.core.uploads import read_image_data_url
from app.services import i18n, monitor, weather
from app.services.memory import memory

logger = logging.getLogger("krishimitra.api")

router = APIRouter(prefix="/api")


class ConsultRequest(BaseModel):
    query: str


class CropIn(BaseModel):
    name: str
    stage: str | None = None
    area_acres: float | None = None


class FarmCreate(BaseModel):
    farmer: str
    location: str  # "City, State" - geocoded server-side
    state: str | None = None
    phone: str | None = None  # for WhatsApp alerts (E.164 or 10-digit)
    farm_size_acres: float = 1
    farming_type: str = "Natural Farming"
    language: str = "hi"
    crops: list[CropIn] = Field(default_factory=list)
    soil: dict[str, Any] = Field(default_factory=dict)
    inputs_on_hand: list[str] = Field(default_factory=list)


class CroppingRequest(BaseModel):
    land: str = "2 acres"
    location: str = "Hisar, Haryana"
    goals: str = "Start natural farming with mixed income and soil building"


class WeeklyRequest(BaseModel):
    focus: str = ""


class TranslateRequest(BaseModel):
    lang: str
    strings: list[str]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "krishimitra"}


@router.get("/farm/exists")
async def farm_exists(user: str = Depends(get_current_user)) -> dict[str, bool]:
    return {"exists": await memory.farm_exists(user)}


@router.get("/farm")
async def get_farm(user: str = Depends(get_current_user)) -> dict[str, Any]:
    if not await memory.farm_exists(user):
        raise HTTPException(404, "No farm yet - complete onboarding")
    return {"farm": await memory.get_farm(user), "recent_activity": await memory.recent_events(10, user)}


@router.post("/farm")
async def create_farm(body: FarmCreate, user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Create / replace the signed-in user's farm. Tries to geocode the location;
    if the weather key isn't set yet, the farm is still created and coordinates
    are resolved lazily later (so onboarding never hard-blocks)."""
    state = body.state or _state_from_location(body.location)
    farm = body.model_dump()
    farm["state"] = state
    try:
        coords = await weather.geocode(body.location)
        farm.update({"lat": coords["lat"], "lon": coords["lon"]})
    except weather.ExternalDataError:
        farm.update({"lat": None, "lon": None})  # resolved later via ensure_coords

    saved = await memory.save_farm(farm, user)
    await memory.add_event("onboarding", f"Farm created in {body.location}", None, user)
    return {"farm": saved}


@router.patch("/farm")
async def update_farm(patch: dict[str, Any], user: str = Depends(get_current_user)) -> dict[str, Any]:
    if not await memory.farm_exists(user):
        raise HTTPException(404, "No farm yet - complete onboarding")
    farm = await memory.update_farm(patch, user)
    # language/crops/etc. changed → rebuild the dashboard (also re-localizes it)
    flows.invalidate_dashboard(user)
    return {"farm": farm}


@router.get("/dashboard")
async def get_dashboard(
    user: str = Depends(get_current_user),
    refresh: bool = Query(False, description="Bypass the cache and rebuild from live data + AI"),
) -> dict[str, Any]:
    if not await memory.farm_exists(user):
        raise HTTPException(404, "No farm yet - complete onboarding")
    return await flows.dashboard(user, force=refresh)


@router.post("/consult", dependencies=[Depends(user_rate_limit(settings.limit_consult, "consult"))])
async def consult(req: ConsultRequest, user: str = Depends(get_current_user)) -> dict[str, Any]:
    if not await memory.farm_exists(user):
        raise HTTPException(404, "No farm yet - complete onboarding")
    try:
        return await orchestrator.consult(req.query, user)
    except guards.GuardRejection as e:
        # Off-topic / empty input: answer politely instead of spending agent calls.
        logger.info("consult rejected (%s) for %s", e.reason, user)
        raise HTTPException(400, e.message)


@router.post("/diagnose", dependencies=[Depends(user_rate_limit(settings.limit_diagnose, "diagnose"))])
async def diagnose(
    file: UploadFile = File(...),
    note: str = Form(""),
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    if not await memory.farm_exists(user):
        raise HTTPException(404, "No farm yet - complete onboarding")
    data_url = await read_image_data_url(file)
    diagnosis = await flows.diagnose_image(data_url, user, guards.sanitize(note))
    flows.invalidate_dashboard(user)  # a new disease record changes health/risk
    return {"diagnosis": diagnosis}


@router.post("/cropping-design")
async def cropping(req: CroppingRequest, user: str = Depends(get_current_user)) -> dict[str, Any]:
    return {"design": await flows.cropping_design(req.land, req.location, req.goals)}


@router.post("/weekly-plan")
async def weekly(req: WeeklyRequest, user: str = Depends(get_current_user)) -> dict[str, Any]:
    if not await memory.farm_exists(user):
        raise HTTPException(404, "No farm yet - complete onboarding")
    return {"plan": await flows.weekly_plan(user, req.focus)}


@router.get("/languages")
async def list_languages() -> dict[str, Any]:
    return {"languages": languages.LANGUAGES}


@router.post("/i18n", dependencies=[Depends(ip_rate_limit(settings.limit_i18n, "i18n"))])
async def translate_ui(req: TranslateRequest) -> dict[str, Any]:
    """Translate a batch of UI strings into `lang` (cached).

    Public by design - the landing page needs it before sign-in and the strings
    aren't sensitive. But it calls the LLM per uncached string, so it's bounded:
    rate-limited by IP, with a cap on batch size and string length. Without those
    caps a loop of unique strings is an open-ended bill.
    """
    if len(req.strings) > settings.i18n_max_strings:
        raise HTTPException(
            413, f"Too many strings - maximum is {settings.i18n_max_strings} per request"
        )
    oversized = [s for s in req.strings if len(s) > settings.i18n_max_string_len]
    if oversized:
        raise HTTPException(
            413,
            f"String exceeds {settings.i18n_max_string_len} characters - "
            "this endpoint translates short UI labels only",
        )
    return {"translations": await i18n.translate(req.strings, req.lang)}


# ---------- soil health card ----------
@router.post("/soil-card", dependencies=[Depends(user_rate_limit(settings.limit_soil_card, "soil_card"))])
async def soil_card(
    file: UploadFile = File(...), user: str = Depends(get_current_user)
) -> dict[str, Any]:
    if not await memory.farm_exists(user):
        raise HTTPException(404, "No farm yet - complete onboarding")
    data_url = await read_image_data_url(file)
    result = await flows.read_soil_card(data_url, user)
    flows.invalidate_dashboard(user)  # updated soil data changes the farm twin
    return result


# ---------- notifications ----------
@router.get("/notifications")
async def notifications(user: str = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "items": await memory.list_notifications(user),
        "unread": await memory.unread_count(user),
    }


@router.post("/notifications/read")
async def mark_read(user: str = Depends(get_current_user)) -> dict[str, bool]:
    await memory.mark_notifications_read(user)
    return {"ok": True}


@router.post(
    "/monitor/run", dependencies=[Depends(user_rate_limit(settings.limit_monitor_run, "monitor_run"))]
)
async def monitor_run(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Run the proactive monitor for the current farm on demand (also runs on a schedule)."""
    if not await memory.farm_exists(user):
        raise HTTPException(404, "No farm yet - complete onboarding")
    created = await monitor.check_farm(await memory.get_farm(user))
    flows.invalidate_dashboard(user)  # surface any new alerts on next load
    return {"alerts_created": created, "unread": await memory.unread_count(user)}


# ---------- Twilio WhatsApp inbound webhook ----------
# No Clerk auth (Twilio can't hold a session) - authenticity comes from the
# X-Twilio-Signature HMAC instead. Without that check the `From` number is
# attacker-controlled and any farm could be impersonated, so an unverified
# request is rejected before any farm lookup or agent call.
@router.post("/whatsapp", dependencies=[Depends(ip_rate_limit(settings.limit_whatsapp, "whatsapp"))])
async def whatsapp_inbound(request: Request) -> Response:
    form = await request.form()

    if settings.twilio_validate_signature:
        params = {k: str(v) for k, v in form.items() if not hasattr(v, "filename")}
        url = twilio_verify.webhook_url(str(request.url))
        signature = request.headers.get("X-Twilio-Signature")
        if not twilio_verify.is_valid_signature(url, params, signature):
            logger.warning("rejected unsigned/invalid WhatsApp webhook from %s", request.client)
            raise HTTPException(403, "Invalid Twilio signature")

    from_number = str(form.get("From", ""))
    body = str(form.get("Body", "")).strip()
    num_media = int(form.get("NumMedia", "0") or 0)

    farm = await memory.farm_by_phone(from_number)
    if not farm:
        return _twiml(
            "Welcome to KrishiMitra! This number isn't linked to a farm yet. "
            "Please sign up and add this phone number in the app to get advice here."
        )
    farm_id = farm["id"]

    try:
        if num_media > 0:
            media_url = str(form.get("MediaUrl0"))
            mime = str(form.get("MediaContentType0", "image/jpeg")).split(";")[0].strip().lower()
            if mime not in settings.allowed_image_type_set:
                return _twiml(
                    "I can only read photos (JPEG, PNG or WebP). Please send a clear "
                    "photo of the affected leaf."
                )
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    media_url, auth=(settings.twilio_account_sid, settings.twilio_auth_token)
                )
            r.raise_for_status()
            if len(r.content) > settings.max_upload_bytes:
                return _twiml("That photo is too large. Please send a smaller image.")
            data_url = f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
            diag = await flows.diagnose_image(data_url, farm_id, guards.sanitize(body))
            reply = _format_diagnosis(diag)
        elif body:
            res = await orchestrator.consult(body, farm_id)
            reply = _format_consult(res)
        else:
            reply = "Send me a question about your crops, or a photo of an affected leaf."
    except guards.GuardRejection as e:
        reply = e.message  # off-topic / empty: reply politely, don't run the agents
    except Exception:
        logger.exception("whatsapp handler failed for farm %s", farm_id)
        reply = "Sorry, something went wrong. Please try again in a moment."
    return _twiml(reply)


def _twiml(message: str) -> Response:
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    xml = f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{safe}</Message></Response>"
    return Response(content=xml, media_type="application/xml")


def _format_consult(res: dict[str, Any]) -> str:
    r = res.get("result", {})
    out = r.get("answer_local") or r.get("answer_en") or "No advice available."
    steps = r.get("action_plan", [])[:3]
    if steps:
        out += "\n\n" + "\n".join(f"{s['step']}. {s['action']} ({s.get('when','')})" for s in steps)
    return out


def _format_diagnosis(diag: dict[str, Any]) -> str:
    if diag.get("issue"):
        out = f"🌿 {diag['issue']} ({diag.get('severity','?')} severity, {int(diag.get('confidence',0)*100)}%)"
        t = diag.get("natural_treatment", {})
        if t.get("remedy"):
            out += f"\n\nTreatment: {t['remedy']}"
            if t.get("recipe"):
                out += f"\nRecipe: {t['recipe']}"
        if diag.get("explanation_local"):
            out += f"\n\n{diag['explanation_local']}"
        return out
    return "I couldn't read that photo clearly. Please send a closer, well-lit photo of the affected leaf."


def _state_from_location(location: str) -> str | None:
    parts = [p.strip() for p in location.split(",")]
    return parts[-1] if len(parts) >= 2 else None
