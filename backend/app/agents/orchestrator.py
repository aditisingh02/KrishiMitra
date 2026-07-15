"""Agent orchestration - the agentic core.

Flow:  query -> Planner -> task graph -> specialist agents (parallel) ->
       Action Planner synthesis -> persisted to Farm Memory.

Every specialist is the same Fireworks model with a different system prompt, so
the "multi-agent" behaviour is real: distinct roles, distinct context, composed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.agents import prompts
from app.core import languages
from app.core.config import settings
from app.core.fireworks import fireworks
from app.services import knowledge, market, weather
from app.services.memory import memory

logger = logging.getLogger("krishimitra.orchestrator")

VALID_TASKS = {"crop_health", "natural_farming", "weather", "market", "finance", "risk"}


async def plan_tasks(query: str, farm_ctx: str) -> dict[str, Any]:
    user = f"FARM CONTEXT:\n{farm_ctx}\n\nFARMER REQUEST:\n{query}"
    result = await fireworks.chat_json(
        prompts.PLANNER, user, model=settings.model_planner, max_tokens=800
    )
    tasks = [t for t in result.get("tasks", []) if t in VALID_TASKS]
    if not tasks:  # safe default
        tasks = ["crop_health", "natural_farming"]
    result["tasks"] = tasks
    return result


# ---------- individual specialist runners ----------
async def _run_crop_health(query: str, farm_ctx: str) -> dict[str, Any]:
    kb = knowledge.context_for(query)
    user = f"FARM CONTEXT:\n{farm_ctx}\n\nKNOWLEDGE BASE:\n{kb}\n\nSYMPTOMS / REQUEST:\n{query}"
    return await fireworks.chat_json(prompts.CROP_HEALTH, user, model=settings.model_agent)


async def _run_natural_farming(query: str, farm_ctx: str, diagnosis: dict | None) -> dict[str, Any]:
    kb = knowledge.context_for((diagnosis or {}).get("issue", "") + " " + query)
    diag = json.dumps(diagnosis) if diagnosis else "Not yet diagnosed - infer from symptoms."
    user = f"DIAGNOSIS:\n{diag}\n\nKNOWLEDGE BASE:\n{kb}\n\nREQUEST:\n{query}"
    return await fireworks.chat_json(prompts.NATURAL_FARMING, user, model=settings.model_agent)


def _coords(farm: dict[str, Any]) -> tuple[float, float]:
    lat, lon = farm.get("lat"), farm.get("lon")
    if lat is None or lon is None:
        raise weather.ExternalDataError("Farm location not set - complete onboarding.")
    return float(lat), float(lon)


def _crop_names(farm: dict[str, Any]) -> list[str]:
    return [c["name"] if isinstance(c, dict) else c for c in farm.get("crops", [])]


async def _run_weather(query: str, farm: dict[str, Any]) -> dict[str, Any]:
    lat, lon = _coords(farm)
    fc = await weather.get_forecast(lat, lon)
    user = f"FORECAST:\n{json.dumps(fc)}\n\nFARMER REQUEST:\n{query}"
    out = await fireworks.chat_json(prompts.WEATHER, user, model=settings.model_fast)
    out["_forecast"] = fc
    return out


async def _run_market(query: str, farm: dict[str, Any]) -> dict[str, Any]:
    crops = _crop_names(farm)
    prices = await market.get_prices(crops, farm.get("state"))
    user = f"MARKET DATA:\n{json.dumps(prices)}\n\nFARMER REQUEST:\n{query}"
    out = await fireworks.chat_json(prompts.MARKET, user, model=settings.model_fast)
    out["_prices"] = prices
    return out


async def _run_finance(query: str, farm: dict[str, Any]) -> dict[str, Any]:
    kb = knowledge.context_for("PM-KISAN PKVY crop insurance scheme subsidy " + query, k=4)
    user = f"FARM PROFILE:\n{json.dumps(farm)}\n\nSCHEME KNOWLEDGE:\n{kb}\n\nREQUEST:\n{query}"
    return await fireworks.chat_json(prompts.FINANCE, user, model=settings.model_agent)


async def _run_risk(query: str, farm: dict[str, Any], farm_id: str, wx: dict | None) -> dict[str, Any]:
    if wx and wx.get("_forecast"):
        fc = wx["_forecast"]
    else:
        lat, lon = _coords(farm)
        fc = await weather.get_forecast(lat, lon)
    user = (
        f"FARM:\n{json.dumps(farm)}\n\nFORECAST:\n{json.dumps(fc)}\n\n"
        f"RECENT ACTIVITY:\n{json.dumps(memory.recent_events(5, farm_id))}\n\nREQUEST:\n{query}"
    )
    return await fireworks.chat_json(prompts.RISK, user, model=settings.model_agent)


# ---------- main entry ----------
async def consult(query: str, farm_id: str) -> dict[str, Any]:
    from app.agents.flows import ensure_coords  # local import avoids any cycle

    farm = await ensure_coords(farm_id, memory.get_farm(farm_id))
    farm_ctx = memory.context_blob(farm_id)

    plan = await plan_tasks(query, farm_ctx)
    tasks = plan["tasks"]
    logger.info("Planner chose: %s", tasks)

    outputs: dict[str, Any] = {}

    # crop_health must finish before natural_farming (dependency).
    if "crop_health" in tasks:
        outputs["crop_health"] = await _run_crop_health(query, farm_ctx)

    # weather before risk (dependency). External calls may fail - capture, don't crash.
    parallel: dict[str, asyncio.Task] = {}
    if "weather" in tasks:
        try:
            outputs["weather"] = await _run_weather(query, farm)
        except Exception as e:
            logger.warning("weather failed: %s", e)
            outputs["weather"] = {"error": str(e)}
    if "natural_farming" in tasks:
        parallel["natural_farming"] = asyncio.create_task(
            _run_natural_farming(query, farm_ctx, outputs.get("crop_health"))
        )
    if "market" in tasks:
        parallel["market"] = asyncio.create_task(_run_market(query, farm))
    if "finance" in tasks:
        parallel["finance"] = asyncio.create_task(_run_finance(query, farm))
    if "risk" in tasks:
        wx = outputs.get("weather") if not outputs.get("weather", {}).get("error") else None
        parallel["risk"] = asyncio.create_task(_run_risk(query, farm, farm_id, wx))

    for name, task in parallel.items():
        try:
            outputs[name] = await task
        except Exception as e:  # one agent failing shouldn't kill the consult
            logger.exception("agent %s failed", name)
            outputs[name] = {"error": str(e)}

    # ---- synthesis ----
    lang_name = languages.name(farm.get("language"))
    synth_user = (
        f"TARGET LANGUAGE for answer_local: {lang_name}\n\n"
        f"FARM CONTEXT:\n{farm_ctx}\n\nFARMER QUESTION:\n{query}\n\n"
        f"SPECIALIST OUTPUTS:\n{json.dumps(outputs, ensure_ascii=False)}"
    )
    final = await fireworks.chat_json(
        prompts.ACTION_PLANNER, synth_user, model=settings.model_agent, max_tokens=1400
    )

    # persist & record diagnosis if any
    diag = outputs.get("crop_health")
    if diag and diag.get("issue") and not diag.get("error"):
        crop = farm.get("crops", [{}])
        crop_name = crop[0]["name"] if crop and isinstance(crop[0], dict) else "crop"
        memory.record_disease(diag["issue"], crop_name, farm_id)
    memory.add_event("consult", query[:120], {"intent": plan.get("intent")}, farm_id)

    return {
        "query": query,
        "plan": plan,
        "agents_run": list(outputs.keys()),
        "agent_outputs": outputs,
        "result": final,
        "language": languages.info(farm.get("language")),
    }
