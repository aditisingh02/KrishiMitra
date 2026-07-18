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
from datetime import date, timedelta

from app.agents import flows
from app.core.config import settings
from app.services import notify
from app.services.memory import memory

logger = logging.getLogger("krishimitra.monitor")


async def persist_alerts(farm_id: str, alerts: list[dict]) -> int:
    """Store warning/danger alerts as in-app notifications. Returns how many are new.

    In-app only (WhatsApp is inbound Q&A now, no push). De-duped per farm per day,
    so this is safe to call on every dashboard open AND every monitor cycle: the
    same alert is stored at most once a day, and the notifications table becomes a
    running history the farmer sees whenever they open the app.
    """
    created = 0
    for alert in alerts:
        if alert.get("level") not in {"warning", "danger"}:
            continue
        title = alert["text"][:60]
        if await memory.notification_exists_today(farm_id, title):
            continue
        await memory.add_notification(farm_id, alert["level"], title, alert["text"])
        created += 1
    return created


async def check_farm(farm: dict) -> int:
    """Evaluate one farm and persist any urgent alerts. Returns count created."""
    farm_id = farm.get("id")
    if not farm_id:
        return 0
    try:
        data = await flows.dashboard(farm_id)
    except Exception as e:  # never let one farm break the loop
        logger.warning("monitor: dashboard failed for %s: %s", farm_id, e)
        return 0

    created = await persist_alerts(farm_id, data.get("alerts", []))
    if created:
        logger.info("monitor: %s new alerts for %s", created, farm_id)
    return created


async def check_calendar(farm: dict) -> int:
    """Raise in-app reminders for crop-calendar tasks coming due. Returns count.

    Reminders fire `calendar_reminder_lead_days` ahead so there's time to act
    (buy neem, prepare Jeevamrut) rather than on the day itself.

    A task is reminded exactly once: `notified_on` is stamped after, and
    `due_tasks` only returns un-notified ones. Without that, a daily monitor would
    re-raise the same reminder every day until the task was ticked off.

    In-app only - proactive WhatsApp reminders were removed (WhatsApp is inbound
    Q&A now). The farmer sees these in the app's notification bell.
    """
    farm_id = farm.get("id")
    if not farm_id:
        return 0

    horizon = (date.today() + timedelta(days=settings.calendar_reminder_lead_days)).isoformat()
    try:
        tasks = await memory.due_tasks(farm_id, horizon)
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor: calendar lookup failed for %s: %s", farm_id, e)
        return 0
    if not tasks:
        return 0

    today = date.today().isoformat()
    sent = 0
    for task in tasks[: settings.calendar_reminders_per_cycle]:
        body = task["detail"] or task["title"]
        await memory.add_notification(farm_id, "info", task["title"][:60], body)
        await memory.mark_task_notified(task["id"], today)
        sent += 1

    if sent:
        logger.info("monitor: %s calendar reminders for %s", sent, farm_id)
    return sent


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
            # Risk alerts and calendar reminders are independent: a failure in one
            # must not cost the farmer the other.
            alerts = await check_farm(farm)
            try:
                alerts += await check_calendar(farm)
            except Exception as e:  # noqa: BLE001
                logger.warning("monitor: calendar failed for %s: %s", farm.get("id"), e)
            return alerts

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
