"""Crop calendar generation + proactive reminders (P2 item 15)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.agents import flows
from app.services import monitor

SOW = date(2026, 3, 1)
SOWN_ON = SOW.isoformat()


# ---------- offset -> date conversion ----------
def test_offset_becomes_an_absolute_date():
    """The model gives day offsets; we do the arithmetic. Models are unreliable at
    date maths and a reminder on the wrong day is worse than no reminder."""
    t = flows._calendar_task({"day_offset": 21, "title": "Jeevamrut", "kind": "nutrition"}, SOW)
    assert t["due_on"] == "2026-03-22"  # 1 Mar + 21 days
    assert t["kind"] == "nutrition"


def test_day_zero_is_sowing_day():
    t = flows._calendar_task({"day_offset": 0, "title": "Treat seeds", "kind": "sowing"}, SOW)
    assert t["due_on"] == SOWN_ON


def test_offset_crossing_month_and_year():
    t = flows._calendar_task({"day_offset": 365, "title": "x", "kind": "harvest"}, SOW)
    assert t["due_on"] == "2027-03-01"


# ---------- malformed model output is dropped, never defaulted ----------
@pytest.mark.parametrize(
    "raw",
    [
        {"title": "no offset"},                       # missing offset
        {"day_offset": "soon", "title": "x"},         # non-numeric
        {"day_offset": None, "title": "x"},
        {"day_offset": -5, "title": "x"},             # before sowing
        {"day_offset": 9999, "title": "x"},           # absurd
        {"day_offset": 10},                            # no title
        {"day_offset": 10, "title": "   "},           # blank title
        "not a dict",
        None,
    ],
)
def test_malformed_tasks_are_dropped(raw):
    """A bad task must vanish, not silently default to day 0 - that would fire a
    reminder immediately and teach the farmer to ignore reminders."""
    assert flows._calendar_task(raw, SOW) is None


def test_unknown_kind_falls_back_to_other():
    t = flows._calendar_task({"day_offset": 5, "title": "x", "kind": "nuclear"}, SOW)
    assert t["kind"] == "other"


def test_long_text_is_truncated():
    t = flows._calendar_task({"day_offset": 5, "title": "x" * 500, "detail": "y" * 900}, SOW)
    assert len(t["title"]) <= 120
    assert len(t["detail"]) <= 500


# ---------- duration ----------
def test_duration_uses_model_value_when_sane():
    tasks = [{"due_on": "2026-03-10"}]
    assert flows._clamp_duration(110, tasks, SOW) == 110


@pytest.mark.parametrize("bad", [0, -5, 99999, "long", None])
def test_insane_duration_derives_from_tasks(bad):
    tasks = [{"due_on": "2026-06-09"}]  # 100 days after sowing
    assert flows._clamp_duration(bad, tasks, SOW) == 100


# ---------- generation ----------
@pytest.fixture
def _gen(monkeypatch):
    async def fake_farm(farm_id):
        return {"location": "Hisar, Haryana", "state": "Haryana", "soil": {}}

    monkeypatch.setattr(flows.memory, "get_farm", fake_farm)


@pytest.mark.asyncio
async def test_generate_builds_sorted_dated_tasks(monkeypatch, _gen):
    async def fake_chat_json(system, user, **kw):
        return {
            "crop": "Tomato",
            "duration_days": 110,
            "tasks": [
                {"day_offset": 21, "title": "Jeevamrut 200L per acre", "kind": "nutrition"},
                {"day_offset": 0, "title": "Treat seeds with Beejamrut", "kind": "sowing"},
                {"day_offset": 45, "title": "Neem oil 5ml per litre", "kind": "spray"},
            ],
        }

    monkeypatch.setattr(flows.fireworks, "chat_json", fake_chat_json)
    out = await flows.generate_calendar("farm1", "Tomato", SOWN_ON)

    assert [t["due_on"] for t in out["tasks"]] == ["2026-03-01", "2026-03-22", "2026-04-15"]
    assert out["expected_harvest_on"] == "2026-06-19"  # 1 Mar + 110
    assert out["duration_days"] == 110


@pytest.mark.asyncio
async def test_correct_dosages_across_different_preparations_are_not_flagged(monkeypatch, _gen):
    """Regression: the safety check must run per-task, not over the whole calendar.

    Checking the calendar as one blob pools every quantity and compares it against
    the union of KB entries named anywhere in the text. A correct neem dose
    (5ml/litre, exactly what the KB says) then gets checked against Jeevamrut's
    quantities - because a *different* task mentioned Jeevamrut - and is wrongly
    rejected, killing an otherwise perfect calendar.
    """

    async def fake_chat_json(system, user, **kw):
        return {
            "duration_days": 110,
            "tasks": [
                # Each dosage below is exactly what the KB states for its own prep.
                {"day_offset": 0, "title": "Treat seeds with Beejamrut", "kind": "sowing"},
                {"day_offset": 21, "title": "Apply Jeevamrut 200L per acre", "kind": "nutrition"},
                {"day_offset": 45, "title": "Neem oil 5ml per litre of water", "kind": "spray"},
            ],
        }

    monkeypatch.setattr(flows.fireworks, "chat_json", fake_chat_json)
    out = await flows.generate_calendar("farm1", "Tomato", SOWN_ON)
    assert len(out["tasks"]) == 3


@pytest.mark.asyncio
async def test_generate_rejects_prohibited_chemicals(monkeypatch, _gen):
    """The safety guardrail runs on calendars too - these are dosages a farmer
    acts on weeks later, with nobody watching the model."""

    async def fake_chat_json(system, user, **kw):
        return {
            "duration_days": 90,
            "tasks": [{"day_offset": 30, "title": "Spray monocrotophos", "kind": "spray"}],
        }

    monkeypatch.setattr(flows.fireworks, "chat_json", fake_chat_json)
    with pytest.raises(ValueError, match="couldn't verify"):
        await flows.generate_calendar("farm1", "Tomato", SOWN_ON)


@pytest.mark.asyncio
async def test_generate_raises_on_parse_error(monkeypatch, _gen):
    async def fake_chat_json(system, user, **kw):
        return {"_raw": "junk", "_parse_error": True}

    monkeypatch.setattr(flows.fireworks, "chat_json", fake_chat_json)
    with pytest.raises(ValueError):
        await flows.generate_calendar("farm1", "Tomato", SOWN_ON)


@pytest.mark.asyncio
async def test_generate_raises_when_every_task_is_junk(monkeypatch, _gen):
    async def fake_chat_json(system, user, **kw):
        return {"duration_days": 90, "tasks": [{"nonsense": True}, {"day_offset": -1}]}

    monkeypatch.setattr(flows.fireworks, "chat_json", fake_chat_json)
    with pytest.raises(ValueError):
        await flows.generate_calendar("farm1", "Tomato", SOWN_ON)


# ---------- reminders ----------
def _task(i: int, due: date, **kw):
    return {"id": i, "title": f"Task {i}", "detail": None, "due_on": due.isoformat(), **kw}


@pytest.fixture
def _rem(monkeypatch):
    sent: list = []
    notified: list = []

    async def localize_task(task, lang):
        return task["title"]

    async def send_alert(phone, farmer, body, lang):
        sent.append(body)
        return True

    async def add_notification(farm_id, level, title, body):
        return 1

    async def mark_notified(task_id, on_date):
        notified.append(task_id)

    monkeypatch.setattr(monitor.notify, "localize_task", localize_task)
    monkeypatch.setattr(monitor.notify, "send_alert", send_alert)
    monkeypatch.setattr(monitor.memory, "add_notification", add_notification)
    monkeypatch.setattr(monitor.memory, "mark_task_notified", mark_notified)
    return sent, notified


@pytest.mark.asyncio
async def test_due_tasks_are_reminded_and_marked(monkeypatch, _rem):
    sent, notified = _rem
    soon = date.today() + timedelta(days=1)

    async def due_tasks(farm_id, horizon):
        return [_task(1, soon)]

    monkeypatch.setattr(monitor.memory, "due_tasks", due_tasks)
    n = await monitor.check_calendar({"id": "f1", "phone": "9876543210", "farmer": "R"})
    assert n == 1
    assert sent == ["Task 1"]
    assert notified == [1], "task must be stamped so it isn't reminded again tomorrow"


@pytest.mark.asyncio
async def test_reminder_uses_lead_time_horizon(monkeypatch, _rem):
    """Reminders fire ahead of the due date so there's time to prepare."""
    seen: list[str] = []

    async def due_tasks(farm_id, horizon):
        seen.append(horizon)
        return []

    monkeypatch.setattr(monitor.settings, "calendar_reminder_lead_days", 2)
    monkeypatch.setattr(monitor.memory, "due_tasks", due_tasks)
    await monitor.check_calendar({"id": "f1"})
    assert seen == [(date.today() + timedelta(days=2)).isoformat()]


@pytest.mark.asyncio
async def test_reminders_are_capped_per_cycle(monkeypatch, _rem):
    """A backlog must not become a wall of WhatsApp messages."""
    sent, _ = _rem
    soon = date.today()

    async def due_tasks(farm_id, horizon):
        return [_task(i, soon) for i in range(20)]

    monkeypatch.setattr(monitor.settings, "calendar_reminders_per_cycle", 3)
    monkeypatch.setattr(monitor.memory, "due_tasks", due_tasks)
    n = await monitor.check_calendar({"id": "f1", "phone": "9876543210"})
    assert n == 3
    assert len(sent) == 3


@pytest.mark.asyncio
async def test_failed_send_is_not_marked_notified(monkeypatch, _rem):
    """Don't swallow a reminder: leave it un-stamped so the next cycle retries."""
    _, notified = _rem

    async def due_tasks(farm_id, horizon):
        return [_task(1, date.today())]

    async def failing_send(phone, farmer, body, lang):
        return False

    monkeypatch.setattr(monitor.memory, "due_tasks", due_tasks)
    monkeypatch.setattr(monitor.notify, "send_alert", failing_send)
    n = await monitor.check_calendar({"id": "f1", "phone": "9876543210"})
    assert n == 0
    assert notified == []


@pytest.mark.asyncio
async def test_farm_without_phone_still_gets_in_app_notification(monkeypatch, _rem):
    sent, notified = _rem

    async def due_tasks(farm_id, horizon):
        return [_task(1, date.today())]

    monkeypatch.setattr(monitor.memory, "due_tasks", due_tasks)
    n = await monitor.check_calendar({"id": "f1"})  # no phone
    assert n == 1
    assert sent == []          # no WhatsApp
    assert notified == [1]     # but recorded in-app


@pytest.mark.asyncio
async def test_no_due_tasks_is_a_noop(monkeypatch, _rem):
    async def due_tasks(farm_id, horizon):
        return []

    monkeypatch.setattr(monitor.memory, "due_tasks", due_tasks)
    assert await monitor.check_calendar({"id": "f1", "phone": "9"}) == 0


@pytest.mark.asyncio
async def test_calendar_lookup_failure_is_contained(monkeypatch, _rem):
    async def boom(farm_id, horizon):
        raise RuntimeError("db down")

    monkeypatch.setattr(monitor.memory, "due_tasks", boom)
    assert await monitor.check_calendar({"id": "f1"}) == 0  # must not raise
