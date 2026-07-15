"""Standalone agent flows: vision diagnosis, proactive dashboard, cropping
designer and the weekly coach. All scoped to the authenticated farm_id."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.agents import prompts
from app.core import languages
from app.core.config import settings
from app.core.fireworks import fireworks
from app.services import i18n, knowledge, market, weather
from app.services.memory import memory

logger = logging.getLogger("krishimitra.flows")

# Per-farm cache of the fully-built dashboard payload. The dashboard runs an LLM
# risk agent on every call, so without this every page refresh burns AI credits.
# Keyed by farm_id -> (built_at_epoch, payload).
_dashboard_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def invalidate_dashboard(farm_id: str) -> None:
    """Drop the cached dashboard so the next load rebuilds it (fresh AI + data)."""
    _dashboard_cache.pop(farm_id, None)


async def ensure_coords(farm_id: str, farm: dict[str, Any]) -> dict[str, Any]:
    """Resolve & persist lat/lon from the farm's location if missing and the
    weather key is available. Returns the (possibly updated) farm."""
    if farm.get("lat") is not None and farm.get("lon") is not None:
        return farm
    location = farm.get("location")
    if not location:
        return farm
    try:
        coords = await weather.geocode(location)
    except weather.ExternalDataError:
        return farm
    return await memory.update_farm({"lat": coords["lat"], "lon": coords["lon"]}, farm_id)


async def diagnose_image(image_data_url: str, farm_id: str, note: str = "") -> dict[str, Any]:
    farm = await memory.get_farm(farm_id)
    lang = languages.info(farm.get("language"))
    farm_ctx = await memory.context_blob(farm_id)
    prompt = (
        f"TARGET LANGUAGE for explanation_local: {languages.name(farm.get('language'))}\n"
        f"Farm context: {farm_ctx}\n"
        f"Farmer note: {note or 'none'}\n"
        "Analyze this crop photo and respond in the required JSON schema."
    )
    result = await fireworks.vision(
        prompt, image_data_url, system=prompts.VISION_DIAGNOSIS, model=settings.model_vision
    )
    if isinstance(result, dict) and result.get("issue") and result.get("category") != "healthy":
        crop_guess = result.get("crop_guess", "crop")
        await memory.record_disease(result["issue"], crop_guess, farm_id)
        # store the diagnosis as recallable long-term memory
        remedy = (result.get("natural_treatment") or {}).get("remedy", "")
        await memory.add_memory(
            farm_id,
            "diagnosis",
            f"{result['issue']} on {crop_guess} ({result.get('severity', '?')} severity). {remedy}".strip(),
            {"issue": result["issue"], "crop": crop_guess, "severity": result.get("severity")},
        )
    if isinstance(result, dict):
        result["language"] = lang
        return result
    return {"_raw": result}


async def read_soil_card(image_data_url: str, farm_id: str) -> dict[str, Any]:
    """Extract soil values from a Soil Health Card photo and merge into the farm twin."""
    result = await fireworks.vision(
        "Extract the soil values from this Soil Health Card.",
        image_data_url,
        system=prompts.SOIL_CARD,
        model=settings.model_vision,
    )
    if isinstance(result, dict) and result.get("readable") and not result.get("_parse_error"):
        soil = {k: v for k, v in result.items() if k not in {"readable", "_raw", "_parse_error"} and v is not None}
        farm = await memory.get_farm(farm_id)
        merged = {**farm.get("soil", {}), **soil}
        await memory.update_farm({"soil": merged}, farm_id)
        await memory.add_event("soil_card", "Soil Health Card imported", soil, farm_id)
        return {"soil": merged, "extracted": result}
    farm = await memory.get_farm(farm_id)
    return {"soil": farm.get("soil", {}), "extracted": result}


async def cropping_design(land: str, location: str, goals: str) -> dict[str, Any]:
    kb = knowledge.context_for("natural farming mulching intercropping nitrogen " + goals)
    user = f"LAND: {land}\nLOCATION: {location}\nGOALS: {goals}\nKNOWLEDGE:\n{kb}"
    return await fireworks.chat_json(prompts.CROPPING_DESIGNER, user, model=settings.model_agent)


async def weekly_plan(farm_id: str, focus: str = "") -> dict[str, Any]:
    farm = await ensure_coords(farm_id, await memory.get_farm(farm_id))
    weather_blob = "unavailable"
    if farm.get("lat") is not None and farm.get("lon") is not None:
        try:
            weather_blob = json.dumps(await weather.get_forecast(farm["lat"], farm["lon"]))
        except weather.ExternalDataError as e:
            weather_blob = str(e)
    recent = await memory.recent_events(5, farm_id)
    user = (
        f"FARM:\n{json.dumps(farm)}\n\nFORECAST:\n{weather_blob}\n\n"
        f"RECENT:\n{json.dumps(recent)}\n\nFOCUS: {focus or 'general'}"
    )
    return await fireworks.chat_json(prompts.WEEKLY_COACH, user, model=settings.model_agent, max_tokens=1400)


async def dashboard(farm_id: str, force: bool = False) -> dict[str, Any]:
    """Proactive farm dashboard. External sections fail independently so the
    page still renders with clear per-section error messages.

    Cached per farm for `dashboard_cache_ttl_minutes` to avoid re-running the LLM
    risk agent (and external fetches) on every page load. Pass force=True to rebuild.
    """
    if not force:
        hit = _dashboard_cache.get(farm_id)
        if hit and time.time() - hit[0] < settings.dashboard_cache_ttl_minutes * 60:
            return hit[1]

    farm = await ensure_coords(farm_id, await memory.get_farm(farm_id))
    crops = [c["name"] if isinstance(c, dict) else c for c in farm.get("crops", [])]

    # Every external section fails independently - the dashboard must never 500,
    # and must stay fast: weather first, then market + risk run concurrently with
    # hard timeouts so an unreliable upstream can't hang the request.
    fc: dict[str, Any] | None = None
    weather_error: str | None = None
    try:
        if farm.get("lat") is None or farm.get("lon") is None:
            raise weather.ExternalDataError("Farm location not set - complete onboarding.")
        fc = await asyncio.wait_for(
            weather.get_forecast(float(farm["lat"]), float(farm["lon"])), timeout=12
        )
    except weather.ExternalDataError as e:
        weather_error = str(e)
    except Exception as e:  # noqa: BLE001 - incl. timeout
        logger.warning("dashboard weather failed: %s", e)
        weather_error = "Weather temporarily unavailable."

    async def _market() -> dict[str, Any] | None:
        return await market.get_prices(crops, farm.get("state"))

    async def _risk() -> dict[str, Any]:
        if not fc:
            return {}
        recent = await memory.recent_events(5, farm_id)
        return await fireworks.chat_json(
            prompts.RISK,
            f"FARM:\n{json.dumps(farm)}\n\nFORECAST:\n{json.dumps(fc)}\n\n"
            f"RECENT:\n{json.dumps(recent)}\n\n"
            "Proactively assess the dominant risk for the next 3-5 days.",
            model=settings.model_fast,
            max_tokens=700,
        )

    market_res, risk_res = await asyncio.gather(
        asyncio.wait_for(_market(), timeout=10),
        asyncio.wait_for(_risk(), timeout=25),
        return_exceptions=True,
    )

    prices: dict[str, Any] | None = None
    market_error: str | None = None
    if isinstance(market_res, dict):
        prices = market_res
    elif isinstance(market_res, weather.ExternalDataError):
        market_error = str(market_res)
    elif market_res is not None:
        logger.warning("dashboard market failed: %s", market_res)
        market_error = "Market data temporarily unavailable."

    risk: dict[str, Any] = {}
    if isinstance(risk_res, dict):
        risk = risk_res
    elif isinstance(risk_res, BaseException):
        logger.warning("dashboard risk agent failed: %s", risk_res)

    # derived metrics
    max_rain = max((d["rain_prob"] for d in fc["days"]), default=0) if fc else 0
    risk_score = int(risk.get("score", 0)) if risk and not risk.get("_parse_error") else 0
    health_score = (
        max(35, 100 - risk_score // 2 - (8 if farm.get("recent_diseases") else 0)) if fc else 0
    )
    market_items = prices["items"] if prices else []
    market_positive = sum(1 for i in market_items if i["trend"] == "rising")
    market_trend = "Positive" if market_positive else ("Stable" if market_items else "-")

    # proactive alerts (only from real data)
    alerts: list[dict[str, str]] = []
    if weather_error:
        alerts.append({"level": "danger", "icon": "shield", "text": f"Weather: {weather_error}"})
    if market_error:
        alerts.append({"level": "danger", "icon": "trending", "text": f"Market: {market_error}"})
    if max_rain >= 70:
        alerts.append({"level": "warning", "icon": "rain",
                       "text": f"High rain probability ({max_rain}%) in next days - delay foliar sprays."})
    if risk.get("level") in {"high", "moderate"} and not risk.get("_parse_error"):
        alerts.append({"level": "warning" if risk["level"] == "moderate" else "danger", "icon": "shield",
                       "text": f"{risk.get('primary_risk','Elevated risk')} - {risk.get('mitigation','monitor closely')}."})
    for item in market_items:
        if item["trend"] == "rising":
            alerts.append({"level": "info", "icon": "trending",
                           "text": f"{item['crop']} prices rising - {item['advice']}"})
    if not alerts:
        alerts.append({"level": "ok", "icon": "check", "text": "All clear - no urgent action needed today."})

    # --- localize every farmer-facing string into the farm's language ---
    lang = farm.get("language") or languages.DEFAULT
    if lang and lang != "en":
        pool: list[str] = [a["text"] for a in alerts]
        pool += [i["advice"] for i in market_items] + [i["crop"] for i in market_items]
        pool += [market_trend]
        for k in ("primary_risk", "reason", "mitigation", "window"):
            if isinstance(risk.get(k), str):
                pool.append(risk[k])
        if fc and fc.get("summary"):
            pool.append(fc["summary"])
        tr = await i18n.translate(pool, lang)
        for a in alerts:
            a["text"] = tr.get(a["text"], a["text"])
        market_items = [
            {**i, "advice": tr.get(i["advice"], i["advice"]), "crop": tr.get(i["crop"], i["crop"])}
            for i in market_items
        ]
        market_trend = tr.get(market_trend, market_trend)
        risk = {**risk, **{k: tr.get(risk[k], risk[k]) for k in ("primary_risk", "reason", "mitigation", "window") if isinstance(risk.get(k), str)}}
        if fc and fc.get("summary"):
            fc = {**fc, "summary": tr.get(fc["summary"], fc["summary"])}

    recent_activity = await memory.recent_events(6, farm_id)
    result = {
        "farm": farm,
        "metrics": {
            "health_score": health_score,
            "risk_level": risk.get("level", "unknown"),
            "risk_score": risk_score,
            "rain_probability": max_rain,
            "market_trend": market_trend,
            "recommended_actions": len([a for a in alerts if a["level"] != "ok"]),
        },
        "risk": risk,
        "weather": fc or {"days": [], "summary": weather_error or "", "error": weather_error},
        "market": {"items": market_items, "error": market_error},
        "alerts": alerts,
        "recent_activity": recent_activity,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _dashboard_cache[farm_id] = (time.time(), result)
    return result
