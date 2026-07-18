"""Alerts are persisted (in-app) and accumulate, so the farmer sees them whenever
they open the app - both from the scheduled monitor and on dashboard open."""
from __future__ import annotations

import pytest

from app.services import monitor


@pytest.fixture
def _store(monkeypatch):
    """Capture stored notifications; simulate per-day de-dupe by title."""
    stored: list[tuple] = []
    seen_today: set[str] = set()

    async def exists_today(farm_id, title):
        return title in seen_today

    async def add_notification(farm_id, level, title, body):
        stored.append((level, title, body))
        seen_today.add(title)
        return len(stored)

    monkeypatch.setattr(monitor.memory, "notification_exists_today", exists_today)
    monkeypatch.setattr(monitor.memory, "add_notification", add_notification)
    return stored


ALERTS = [
    {"level": "danger", "icon": "shield", "text": "High rain - delay foliar sprays"},
    {"level": "warning", "icon": "trending", "text": "Powdery mildew risk rising"},
    {"level": "ok", "icon": "check", "text": "All clear"},
    {"level": "info", "icon": "trending", "text": "Tomato prices rising"},
]


@pytest.mark.asyncio
async def test_only_warning_and_danger_are_stored(_store):
    n = await monitor.persist_alerts("f1", ALERTS)
    assert n == 2
    levels = {level for level, _, _ in _store}
    assert levels == {"danger", "warning"}, "ok/info must not become notifications"


@pytest.mark.asyncio
async def test_stored_notifications_persist_the_full_text(_store):
    await monitor.persist_alerts("f1", ALERTS[:1])
    assert _store[0] == ("danger", "High rain - delay foliar sprays", "High rain - delay foliar sprays")


@pytest.mark.asyncio
async def test_same_alert_not_duplicated_within_a_day(_store):
    """Opening the app repeatedly must not pile up duplicate notifications."""
    await monitor.persist_alerts("f1", ALERTS)
    await monitor.persist_alerts("f1", ALERTS)  # second app-open, same day
    await monitor.persist_alerts("f1", ALERTS)
    assert len(_store) == 2, "de-dupe per day failed - notifications would spam"


@pytest.mark.asyncio
async def test_empty_alerts_is_a_noop(_store):
    assert await monitor.persist_alerts("f1", []) == 0
    assert _store == []


@pytest.mark.asyncio
async def test_check_farm_persists_via_dashboard(monkeypatch, _store):
    async def fake_dashboard(farm_id, force=False):
        return {"alerts": ALERTS}

    monkeypatch.setattr(monitor.flows, "dashboard", fake_dashboard)
    n = await monitor.check_farm({"id": "f1"})
    assert n == 2
    assert len(_store) == 2


# ---------- dashboard route persists on open ----------
@pytest.mark.asyncio
async def test_dashboard_open_schedules_persistence(monkeypatch):
    """Opening the app must store current alerts + due reminders (after the
    response), so the bell reflects them without waiting for the daily sweep."""
    from starlette.background import BackgroundTasks
    from app.api import routes

    async def fake_dashboard(farm_id, force=False):
        return {"alerts": ALERTS, "metrics": {}}

    monkeypatch.setattr(routes.flows, "dashboard", fake_dashboard)

    bg = BackgroundTasks()
    await routes.get_dashboard(bg, farm_id="f1", refresh=False)

    funcs = {t.func for t in bg.tasks}
    assert routes.monitor.persist_alerts in funcs, "alerts not persisted on open"
    assert routes.monitor.check_calendar in funcs, "calendar reminders not swept on open"
