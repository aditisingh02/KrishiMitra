"""HTTP API for KrishiMitra. All farm routes require a Clerk-authenticated user;
the farm is keyed by the Clerk user id."""
from __future__ import annotations

import base64
import hmac
import logging
from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.agents import flows, orchestrator
from app.core import guards, languages, twilio_verify
from app.core.auth import get_active_farm, get_current_user
from app.core.config import settings
from app.core.limits import ip_rate_limit, user_rate_limit
from app.core.observability import metrics
from app.core.uploads import downscale_image, read_image_data_url
from app.services import i18n, monitor, notify, weather
from app.services.memory import memory

logger = logging.getLogger("krishimitra.api")

router = APIRouter(prefix="/api")


class ConsultRequest(BaseModel):
    query: str


class CropIn(BaseModel):
    name: str
    stage: str | None = None
    area_acres: float | None = None


def _validate_language(v: str | None) -> str | None:
    if v is not None and v not in languages.LANGUAGES:
        raise ValueError(f"Unsupported language '{v}'")
    return v


def _bound_soil(v: dict[str, Any] | None) -> dict[str, Any] | None:
    # Free-form, but it lands in JSONB and is interpolated into prompts - cap it.
    if v is None:
        return None
    if len(v) > 20:
        raise ValueError("Too many soil fields")
    return {str(k)[:40]: (str(val)[:120] if isinstance(val, str) else val) for k, val in v.items()}


# ---- profile (the farmer) ----
class ProfileCreate(BaseModel):
    """Onboarding step 1: the farmer. Farms are added separately."""

    name: str = Field(min_length=1, max_length=80)
    location: str = Field(min_length=2, max_length=120)  # seeds the first farm
    phone: str | None = Field(default=None, max_length=20)
    language: str = Field(default="hi", max_length=8)

    _lang = field_validator("language")(_validate_language)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    language: str | None = Field(default=None, max_length=8)
    default_location: str | None = Field(default=None, max_length=120)

    _lang = field_validator("language")(_validate_language)


class ActiveFarmRequest(BaseModel):
    farm_id: str


# ---- farm ----
class FarmCreate(BaseModel):
    """Onboarding step 2 / 'add farm'. Identity comes from the profile."""

    name: str = Field(min_length=1, max_length=80)
    location: str = Field(min_length=2, max_length=120)  # geocoded server-side
    state: str | None = None
    farm_size_acres: float = Field(default=1, gt=0, le=100_000)
    farming_type: str = Field(default="Natural Farming", max_length=40)
    crops: list[CropIn] = Field(default_factory=list, max_length=40)
    soil: dict[str, Any] = Field(default_factory=dict)
    inputs_on_hand: list[str] = Field(default_factory=list, max_length=60)

    _soil = field_validator("soil")(_bound_soil)


class FarmUpdate(BaseModel):
    """Validated partial update of one farm. Only fields sent are applied.

    Farm-level only - identity (name/phone/language of the farmer) lives on the
    profile, so it can't be mass-assigned here.
    """

    name: str | None = Field(default=None, min_length=1, max_length=80)
    location: str | None = Field(default=None, min_length=2, max_length=120)
    farm_size_acres: float | None = Field(default=None, gt=0, le=100_000)
    farming_type: str | None = Field(default=None, max_length=40)
    crops: list[CropIn] | None = Field(default=None, max_length=40)
    soil: dict[str, Any] | None = None
    inputs_on_hand: list[str] | None = Field(default=None, max_length=60)

    _soil = field_validator("soil")(_bound_soil)

    @field_validator("inputs_on_hand")
    @classmethod
    def _clean_inputs(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [s.strip()[:60] for s in v if s and s.strip()][:60]


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


async def _geocode_into(data: dict[str, Any], location: str) -> None:
    """Resolve + attach lat/lon for a location. Never blocks - coords resolve
    lazily later via ensure_coords if geocoding is down."""
    try:
        coords = await weather.geocode(location)
        data["lat"], data["lon"] = coords["lat"], coords["lon"]
    except weather.ExternalDataError:
        data["lat"], data["lon"] = None, None
        logger.info("geocode failed for %r - coords will resolve lazily", location)


async def _phone_free_for(user: str, phone: str) -> None:
    """Reject a WhatsApp number already claimed by a different profile.

    Inbound WhatsApp is routed by number (profile_by_phone), so two profiles
    sharing one number would send a farmer's messages to the wrong account.
    """
    owner = await memory.profile_by_phone(phone)
    if owner and owner.get("id") != user:
        raise HTTPException(409, "That WhatsApp number is already linked to another account.")


# ---------- profile (the farmer) ----------
@router.get("/profile/exists")
async def profile_exists(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Drives onboarding routing: no profile -> step 1, profile but no farm -> step 2."""
    profile = await memory.get_profile(user)
    farms = await memory.list_farms(user) if profile else []
    return {
        "profile": profile is not None,
        "farms": len(farms),
        "active_farm_id": (profile or {}).get("active_farm_id"),
    }


@router.get("/profile")
async def get_profile(user: str = Depends(get_current_user)) -> dict[str, Any]:
    profile = await memory.get_profile(user)
    if not profile:
        raise HTTPException(404, "No profile yet - complete onboarding")
    return {"profile": profile, "farms": await memory.list_farms(user)}


@router.post("/profile")
async def create_profile(body: ProfileCreate, user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Onboarding step 1: create/replace the farmer profile."""
    if body.phone and body.phone.strip():
        await _phone_free_for(user, body.phone.strip())
    profile = await memory.save_profile(
        user,
        {
            "name": body.name.strip(),
            "phone": (body.phone or "").strip() or None,
            "language": body.language,
            "default_location": body.location.strip(),
        },
    )
    return {"profile": profile}


@router.patch("/profile")
async def update_profile(body: ProfileUpdate, user: str = Depends(get_current_user)) -> dict[str, Any]:
    if not await memory.profile_exists(user):
        raise HTTPException(404, "No profile yet - complete onboarding")
    patch = body.model_dump(exclude_unset=True)
    patch = {k: v for k, v in patch.items() if v is not None or k == "phone"}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    if "phone" in patch:
        phone = (patch["phone"] or "").strip()
        if phone:
            await _phone_free_for(user, phone)
        patch["phone"] = phone or None  # "" clears the link
    profile = await memory.save_profile(user, patch)
    # Language/name propagate to every farm (denormalized), so rebuild dashboards.
    for farm in await memory.list_farms(user):
        flows.invalidate_dashboard(farm["id"])
    return {"profile": profile}


@router.post("/profile/active-farm")
async def switch_active_farm(body: ActiveFarmRequest, user: str = Depends(get_current_user)) -> dict[str, Any]:
    if not await memory.set_active_farm(user, body.farm_id):
        raise HTTPException(404, "That farm doesn't belong to you.")
    return {"active_farm_id": body.farm_id}


# ---------- farms (a profile owns many) ----------
@router.get("/farms")
async def list_farms(user: str = Depends(get_current_user)) -> dict[str, Any]:
    profile = await memory.get_profile(user)
    return {
        "farms": await memory.list_farms(user),
        "active_farm_id": (profile or {}).get("active_farm_id"),
    }


@router.post("/farms")
async def create_farm(body: FarmCreate, user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Add a farm under the profile. The first farm becomes the active one."""
    if not await memory.profile_exists(user):
        raise HTTPException(404, "Create your profile first.")
    data = body.model_dump()
    data["state"] = body.state or _state_from_location(body.location)
    await _geocode_into(data, body.location)
    farm = await memory.create_farm(user, data)

    # First farm auto-activates so the app has something to show immediately.
    profile = await memory.get_profile(user)
    if not profile.get("active_farm_id"):
        await memory.set_active_farm(user, farm["id"])
    await memory.add_event("farm", f"Farm '{body.name}' added in {body.location}", None, farm["id"])
    return {"farm": farm}


@router.get("/farm")
async def get_active_farm_detail(farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    return {"farm": await memory.get_farm(farm_id), "recent_activity": await memory.recent_events(10, farm_id)}


@router.patch("/farms/{farm_id}")
async def update_farm(farm_id: str, body: FarmUpdate, user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Partial update of one owned farm. Only the fields sent are touched."""
    if not await memory.owns_farm(user, farm_id):
        raise HTTPException(404, "Farm not found")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    if "crops" in patch:
        patch["crops"] = [c for c in patch["crops"] if (c.get("name") or "").strip()]
    if "location" in patch:
        await _geocode_into(patch, patch["location"])  # coords must follow location
    farm = await memory.update_farm(patch, farm_id)
    flows.invalidate_dashboard(farm_id)
    await memory.add_event("farm", "Farm updated", {"fields": sorted(patch)}, farm_id)
    return {"farm": farm}


@router.delete("/farms/{farm_id}")
async def delete_farm(farm_id: str, user: str = Depends(get_current_user)) -> dict[str, Any]:
    if not await memory.delete_farm(user, farm_id):
        raise HTTPException(404, "Farm not found")
    flows.invalidate_dashboard(farm_id)
    return {"ok": True}


@router.get("/dashboard")
async def get_dashboard(
    background: BackgroundTasks,
    farm_id: str = Depends(get_active_farm),
    refresh: bool = Query(False, description="Bypass the cache and rebuild from live data + AI"),
) -> dict[str, Any]:
    data = await flows.dashboard(farm_id, force=refresh)
    # Opening the app stores the current alerts + due calendar reminders as
    # notifications (de-duped per day), so the bell always reflects what the
    # monitor would have caught - the farmer doesn't have to wait for the daily
    # sweep. Runs after the response so it never slows the dashboard.
    background.add_task(monitor.persist_alerts, farm_id, data.get("alerts", []))
    background.add_task(monitor.check_calendar, {"id": farm_id})
    return data


@router.post("/consult", dependencies=[Depends(user_rate_limit(settings.limit_consult, "consult"))])
async def consult(req: ConsultRequest, farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    try:
        return await orchestrator.consult(req.query, farm_id)
    except guards.GuardRejection as e:
        # Off-topic / empty input: answer politely instead of spending agent calls.
        logger.info("consult rejected (%s) for %s", e.reason, farm_id)
        raise HTTPException(400, e.message)


@router.post("/diagnose", dependencies=[Depends(user_rate_limit(settings.limit_diagnose, "diagnose"))])
async def diagnose(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    note: str = Form(""),
    farm_id: str = Depends(get_active_farm),
) -> dict[str, Any]:
    data_url = await read_image_data_url(file)
    diagnosis = await flows.diagnose_image(data_url, farm_id, guards.sanitize(note))
    # After the response: (1) store every scan in the chat history (incl. healthy
    # ones - unconditional, unlike persist_diagnosis), (2) record the disease on the
    # farm twin + embed to memory only when there's a real issue.
    if isinstance(diagnosis, dict) and not diagnosis.get("_parse_error"):
        background.add_task(flows.persist_interaction_diagnose, diagnosis, farm_id)
    if flows.needs_persisting(diagnosis):
        background.add_task(flows.persist_diagnosis, diagnosis, farm_id)
    return {"diagnosis": diagnosis}


@router.get("/consult/history")
async def consult_history(
    limit: int = Query(20, ge=1, le=50), farm_id: str = Depends(get_active_farm)
) -> dict[str, Any]:
    return {"items": await memory.list_interactions(farm_id, "consult", limit)}


@router.get("/diagnose/history")
async def diagnose_history(
    limit: int = Query(20, ge=1, le=50), farm_id: str = Depends(get_active_farm)
) -> dict[str, Any]:
    return {"items": await memory.list_interactions(farm_id, "diagnose", limit)}


@router.post("/cropping-design")
async def cropping(req: CroppingRequest, user: str = Depends(get_current_user)) -> dict[str, Any]:
    return {"design": await flows.cropping_design(req.land, req.location, req.goals)}


@router.post("/weekly-plan")
async def weekly(req: WeeklyRequest, farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    return {"plan": await flows.weekly_plan(farm_id, req.focus)}


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
    file: UploadFile = File(...), farm_id: str = Depends(get_active_farm)
) -> dict[str, Any]:
    data_url = await read_image_data_url(file)
    result = await flows.read_soil_card(data_url, farm_id)
    flows.invalidate_dashboard(farm_id)  # updated soil data changes the farm twin
    return result


# ---------- notifications ----------
# ---------- crop calendar ----------
class CycleCreate(BaseModel):
    crop: str = Field(min_length=1, max_length=60)
    sown_on: str  # ISO date, YYYY-MM-DD


class TaskUpdate(BaseModel):
    done: bool


def _parse_sown_on(value: str) -> date:
    try:
        sown = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "sown_on must be a date like 2026-07-01") from None
    # A sowing date far in the future or decades back is a typo, and it would
    # generate a whole calendar of nonsense reminders.
    today = date.today()
    if sown > today + timedelta(days=365):
        raise HTTPException(400, "That sowing date is too far in the future.")
    if sown < today - timedelta(days=365 * 2):
        raise HTTPException(400, "That sowing date is too far in the past.")
    return sown


@router.get("/calendar")
async def get_calendar(farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    """All crop cycles for the active farm plus their tasks."""
    cycles = await memory.list_cycles(farm_id)
    tasks = await memory.list_tasks(farm_id)
    by_cycle: dict[int, list[dict[str, Any]]] = {}
    for t in tasks:
        by_cycle.setdefault(t["cycle_id"], []).append(t)
    return {
        "cycles": [{**c, "tasks": by_cycle.get(c["id"], [])} for c in cycles],
        "today": date.today().isoformat(),
    }


@router.post(
    "/calendar/cycles",
    dependencies=[Depends(user_rate_limit(settings.limit_calendar, "calendar"))],
)
async def create_cycle(req: CycleCreate, farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    """Start a crop cycle on the active farm and generate its task timeline."""
    _parse_sown_on(req.sown_on)
    crop = guards.sanitize(req.crop)
    if not crop:
        raise HTTPException(400, "Tell me which crop you sowed.")

    try:
        plan = await flows.generate_calendar(farm_id, crop, req.sown_on)
    except ValueError as e:
        # Generation failed or the safety guardrail blocked it - the message is
        # already farmer-readable.
        raise HTTPException(422, str(e)) from None

    cycle_id = await memory.add_cycle(farm_id, crop, req.sown_on, plan["expected_harvest_on"])
    await memory.add_tasks(farm_id, cycle_id, plan["tasks"])
    await memory.add_event(
        "crop_cycle",
        f"Started {crop} cycle (sown {req.sown_on})",
        {"crop": crop, "sown_on": req.sown_on, "tasks": len(plan["tasks"])},
        farm_id,
    )
    flows.invalidate_dashboard(farm_id)
    cycle = await memory.get_cycle(farm_id, cycle_id)
    return {"cycle": {**cycle, "tasks": await memory.list_tasks(farm_id, cycle_id=cycle_id)}}


@router.patch("/calendar/tasks/{task_id}")
async def update_task(
    task_id: int, req: TaskUpdate, farm_id: str = Depends(get_active_farm)
) -> dict[str, Any]:
    if not await memory.set_task_done(farm_id, task_id, req.done):
        raise HTTPException(404, "Task not found")
    return {"ok": True}


@router.delete("/calendar/cycles/{cycle_id}")
async def delete_cycle(cycle_id: int, farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    if not await memory.delete_cycle(farm_id, cycle_id):
        raise HTTPException(404, "Crop cycle not found")
    flows.invalidate_dashboard(farm_id)
    return {"ok": True}


@router.post("/calendar/cycles/{cycle_id}/harvested")
async def mark_harvested(cycle_id: int, farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    if not await memory.set_cycle_status(farm_id, cycle_id, "harvested"):
        raise HTTPException(404, "Crop cycle not found")
    return {"ok": True}


@router.get("/metrics")
async def agent_metrics(request: Request) -> dict[str, Any]:
    """Per-agent latency / failure / token counters.

    Not Clerk-authed: this is for an operator or scraper, not a farmer. Guarded by
    a shared token instead, and disabled entirely by default - it describes
    internal AI spend and shouldn't be world-readable.

    Per-worker and in-memory: a health signal, not billing.
    """
    if not settings.metrics_enabled:
        raise HTTPException(404, "Not found")
    expected = settings.metrics_token
    supplied = request.headers.get("X-Metrics-Token", "")
    # compare_digest avoids leaking the token through response timing.
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "Invalid metrics token")
    return {"agents": metrics.snapshot()}


# ---------- WhatsApp link status ----------
def _mask_phone(digits: str) -> str:
    """Show only the last 4 digits - enough to recognise, not enough to leak."""
    return f"•••••• {digits[-4:]}" if len(digits) >= 4 else "••••••"


@router.get("/whatsapp/status")
async def whatsapp_status(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Whether the farmer can receive WhatsApp alerts, and why not if they can't.

    WhatsApp is profile-level (one number for the farmer, all their farms). Two
    independent things must both be true: the profile has a number, and the server
    has Twilio credentials. The farmer can only fix the first, so report separately.
    """
    profile = await memory.get_profile(user)
    if not profile:
        raise HTTPException(404, "No profile yet - complete onboarding")
    phone = (profile.get("phone") or "").strip()
    return {
        "linked": bool(phone) and notify.configured(),
        "has_phone": bool(phone),
        "provider_configured": notify.configured(),
        "phone_masked": _mask_phone(phone) if phone else None,
        "sandbox_join_code": settings.twilio_sandbox_join_code or None,
    }


@router.post(
    "/whatsapp/test",
    dependencies=[Depends(user_rate_limit(settings.limit_whatsapp_test, "whatsapp_test"))],
)
async def whatsapp_test(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Send a test message so the farmer can confirm the link works.

    Rate-limited hard: it sends a real (billed) message to a user-supplied number.
    """
    profile = await memory.get_profile(user)
    if not profile:
        raise HTTPException(404, "No profile yet - complete onboarding")
    phone = (profile.get("phone") or "").strip()
    if not phone:
        raise HTTPException(400, "Add your WhatsApp number in your profile first.")
    if not notify.configured():
        raise HTTPException(
            503, "WhatsApp isn't configured on the server yet. Please try again later."
        )

    ok = await notify.send_test(phone, profile.get("language"))
    if not ok:
        # Most common cause on the Twilio sandbox: the number never sent the
        # `join <code>` message, so Twilio refuses to deliver to it.
        raise HTTPException(
            502,
            "Couldn't deliver the test message. On the Twilio sandbox you must first "
            "send the join code from your WhatsApp to the sandbox number.",
        )
    return {"sent": True, "to": _mask_phone(phone)}


@router.get("/notifications")
async def notifications(farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    return {
        "items": await memory.list_notifications(farm_id),
        "unread": await memory.unread_count(farm_id),
    }


@router.post("/notifications/read")
async def mark_read(farm_id: str = Depends(get_active_farm)) -> dict[str, bool]:
    await memory.mark_notifications_read(farm_id)
    return {"ok": True}


@router.post(
    "/monitor/run", dependencies=[Depends(user_rate_limit(settings.limit_monitor_run, "monitor_run"))]
)
async def monitor_run(farm_id: str = Depends(get_active_farm)) -> dict[str, Any]:
    """Run the proactive monitor for the active farm on demand (also runs on a schedule)."""
    created = await monitor.check_farm(await memory.get_farm(farm_id))
    flows.invalidate_dashboard(farm_id)  # surface any new alerts on next load
    return {"alerts_created": created, "unread": await memory.unread_count(farm_id)}


# ---------- Twilio WhatsApp inbound webhook ----------
# No Clerk auth (Twilio can't hold a session) - authenticity comes from the
# X-Twilio-Signature HMAC instead. Without that check the `From` number is
# attacker-controlled and any farm could be impersonated, so an unverified
# request is rejected before any farm lookup or agent call.
@router.post("/whatsapp", dependencies=[Depends(ip_rate_limit(settings.limit_whatsapp, "whatsapp"))])
async def whatsapp_inbound(request: Request, background: BackgroundTasks) -> Response:
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

    # WhatsApp is profile-level; advice runs on the profile's active farm.
    profile = await memory.profile_by_phone(from_number)
    if not profile:
        return _twiml(
            "Welcome to KrishiMitra! This number isn't linked to an account yet. "
            "Please sign up and add this phone number in the app to get advice here."
        )
    farm_id = profile.get("active_farm_id")
    if not farm_id or not await memory.farm_exists(farm_id):
        return _twiml(
            "Your account has no active farm yet. Please add a farm in the app first."
        )
    farm = await memory.get_farm(farm_id)

    try:
        if num_media > 0:
            mime = str(form.get("MediaContentType0", "image/jpeg")).split(";")[0].strip().lower()
            if mime not in settings.allowed_image_type_set:
                return _twiml(
                    "I can only read photos (JPEG, PNG or WebP). Please send a clear "
                    "photo of the affected leaf."
                )
            # Vision diagnosis takes ~25-35s - far longer than Twilio's webhook
            # window (~15s), so doing it inline would let the webhook time out and
            # the farmer would get nothing. Instead: ack instantly, then diagnose in
            # the background and PUSH the result as a second message when it's ready.
            # This changes only *when* the answer arrives, never how it's computed.
            background.add_task(
                _diagnose_and_push,
                farm_id,
                from_number,
                str(form.get("MediaUrl0")),
                mime,
                guards.sanitize(body),
                farm.get("language"),
            )
            reply = await notify.localize_text(
                "Got your photo - analysing the leaf now. I'll send your diagnosis in a few seconds. 🌱",
                farm.get("language"),
            )
        elif body:
            # Consult is ~10s (within the webhook window), so it stays inline.
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


async def _diagnose_and_push(
    farm_id: str, to_number: str, media_url: str, mime: str, note: str, lang: str | None
) -> None:
    """Download -> diagnose -> push the result over WhatsApp. Runs after the ack.

    All the slow work lives here, off the webhook's critical path. Any failure is
    turned into a helpful message rather than silence - the farmer is waiting and
    a dropped reply looks like the app is broken.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                media_url, auth=(settings.twilio_account_sid, settings.twilio_auth_token)
            )
        r.raise_for_status()
        if len(r.content) > settings.max_upload_bytes:
            await notify.send_whatsapp(
                to_number, await notify.localize_text("That photo is too large. Please send a smaller image.", lang)
            )
            return

        # No browser here to pre-shrink, so downscale server-side (accuracy floor
        # 1280px - unchanged).
        content, mime = await downscale_image(r.content, mime)
        data_url = f"data:{mime};base64,{base64.b64encode(content).decode()}"

        diag = await flows.diagnose_image(data_url, farm_id, note)
        # Store every scan in history (incl. healthy), same as the web route.
        if isinstance(diag, dict) and not diag.get("_parse_error"):
            await flows.persist_interaction_diagnose(diag, farm_id)
        if flows.needs_persisting(diag):
            await flows.persist_diagnosis(diag, farm_id)  # already backgrounded; just await

        await notify.send_whatsapp(to_number, _format_diagnosis(diag))
    except Exception:
        logger.exception("whatsapp diagnose push failed for farm %s", farm_id)
        await notify.send_whatsapp(
            to_number,
            await notify.localize_text(
                "Sorry, I couldn't read that photo. Please try again with a clear, "
                "well-lit photo of the affected leaf.",
                lang,
            ),
        )


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
