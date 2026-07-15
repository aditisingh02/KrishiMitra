"""Autonomous monitoring.

Periodically runs the proactive dashboard (risk + weather + market agents) for
every farm and turns urgent findings into in-app notifications - and, if the farm
has a phone and Twilio is configured, a WhatsApp push. This is what makes the
system a proactive agronomist rather than request/response only.
"""
from __future__ import annotations

import asyncio
import logging

from app.agents import flows
from app.core.config import settings
from app.services import notify
from app.services.memory import memory

logger = logging.getLogger("krishimitra.monitor")


async def check_farm(farm: dict) -> int:
    """Evaluate one farm; create notifications for urgent alerts. Returns count."""
    farm_id = farm.get("id")
    if not farm_id:
        return 0
    try:
        data = await flows.dashboard(farm_id)
    except Exception as e:  # never let one farm break the loop
        logger.warning("monitor: dashboard failed for %s: %s", farm_id, e)
        return 0

    created = 0
    for alert in data.get("alerts", []):
        if alert["level"] not in {"warning", "danger"}:
            continue
        title = alert["text"][:60]
        if memory.notification_exists_today(farm_id, title):
            continue  # de-dupe per day
        memory.add_notification(farm_id, alert["level"], title, alert["text"])
        created += 1
        phone = farm.get("phone")
        if phone:
            await notify.send_whatsapp(
                phone,
                f"🌱 KrishiMitra alert for {farm.get('farmer','your farm')}:\n\n{alert['text']}",
            )
    if created:
        logger.info("monitor: %s new alerts for %s", created, farm_id)
    return created


async def run_once() -> dict:
    farms = memory.all_farms()
    total = 0
    for farm in farms:
        total += await check_farm(farm)
    return {"farms_checked": len(farms), "alerts_created": total}


async def loop() -> None:
    """Background scheduler - runs run_once() every monitor_interval_hours."""
    await asyncio.sleep(settings.monitor_start_delay_seconds)
    while True:
        try:
            result = await run_once()
            logger.info("monitor cycle: %s", result)
        except Exception:
            logger.exception("monitor cycle failed")
        await asyncio.sleep(settings.monitor_interval_hours * 3600)
