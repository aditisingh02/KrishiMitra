"""Autonomous monitoring.

Periodically runs the proactive dashboard (risk + weather + market agents) for
every farm and turns urgent findings into in-app notifications - and, if the farm
has a phone and Twilio is configured, a WhatsApp push. This is what makes the
system a proactive agronomist rather than request/response only.
"""
from __future__ import annotations

import asyncio
import logging
import time

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
        if await memory.notification_exists_today(farm_id, title):
            continue  # de-dupe per day
        await memory.add_notification(farm_id, alert["level"], title, alert["text"])
        created += 1
        phone = farm.get("phone")
        if phone:
            # alert["text"] is already in the farm's language (dashboard localizes
            # it); send_alert localizes the header that wraps it.
            await notify.send_alert(
                phone,
                farm.get("farmer") or "your farm",
                alert["text"],
                farm.get("language"),
            )
    if created:
        logger.info("monitor: %s new alerts for %s", created, farm_id)
    return created


async def run_once() -> dict:
    """Check every farm, a bounded number at a time.

    Previously this awaited each farm in turn, so a cycle took
    (farms x dashboard latency) - and a dashboard runs an LLM risk agent plus
    weather and market fetches, so ~10s each. At 500 farms that's ~90 minutes of
    wall clock, and it grows linearly: eventually a daily cycle can't finish in a
    day.

    Farms are independent, so run them concurrently. The semaphore is the point:
    unbounded `gather` over every farm would fire N simultaneous LLM calls and
    trip provider rate limits (and our own), turning a slow cycle into a failing
    one.
    """
    farms = await memory.all_farms()
    if not farms:
        return {"farms_checked": 0, "alerts_created": 0}

    started = time.perf_counter()
    sem = asyncio.Semaphore(max(1, settings.monitor_concurrency))

    async def guarded(farm: dict) -> int:
        async with sem:
            return await check_farm(farm)

    results = await asyncio.gather(
        *(guarded(f) for f in farms), return_exceptions=True
    )

    total = 0
    failed = 0
    for farm, res in zip(farms, results):
        if isinstance(res, BaseException):
            # check_farm already guards the dashboard; this catches anything else
            # so one bad farm can't abort the cycle for everyone.
            logger.warning("monitor: farm %s failed: %s", farm.get("id"), res)
            failed += 1
        else:
            total += res

    elapsed = time.perf_counter() - started
    logger.info(
        "monitor cycle: %s farms in %.1fs (concurrency=%s, %s failed)",
        len(farms), elapsed, settings.monitor_concurrency, failed,
    )
    return {
        "farms_checked": len(farms),
        "alerts_created": total,
        "farms_failed": failed,
        "seconds": round(elapsed, 1),
    }


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
