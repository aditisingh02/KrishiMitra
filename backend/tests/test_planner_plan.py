"""Consult action-plan -> dated planner tasks (parse_when, plan_to_tasks, endpoint)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.agents import flows


TODAY = date.today()


# ---------- parse_when ----------
@pytest.mark.parametrize("when", ["Today", "now", "immediately", "right away", "ASAP"])
def test_immediate_maps_to_today(when):
    assert flows.parse_when(when) == TODAY.isoformat()


def test_today_and_then_every_10_days_is_dated_today():
    assert flows.parse_when("Today and then every 10 days") == TODAY.isoformat()


def test_tomorrow():
    assert flows.parse_when("tomorrow morning") == (TODAY + timedelta(days=1)).isoformat()


@pytest.mark.parametrize("when,days", [("in 5 days", 5), ("after 3 days", 3), ("10 days", 10)])
def test_n_days(when, days):
    assert flows.parse_when(when) == (TODAY + timedelta(days=days)).isoformat()


def test_every_n_days_without_today_anchor_is_first_occurrence():
    assert flows.parse_when("every 7 days") == (TODAY + timedelta(days=7)).isoformat()


def test_week_and_month():
    assert flows.parse_when("this week") == (TODAY + timedelta(days=2)).isoformat()
    assert flows.parse_when("next week") == (TODAY + timedelta(days=7)).isoformat()
    assert flows.parse_when("next month") == (TODAY + timedelta(days=30)).isoformat()


@pytest.mark.parametrize(
    "when",
    ["Next planting season", "After first application", "At flowering", "when the plant matures", "", "  "],
)
def test_seasonal_or_relative_is_undated(when):
    """A wrong date is worse than none - these must return None, not guess."""
    assert flows.parse_when(when) is None


def test_absurd_day_count_is_undated():
    assert flows.parse_when("in 900 days") is None


# ---------- plan_to_tasks ----------
STEPS = [
    {"step": 1, "action": "Prepare diluted Jeevamrut (1:10)", "when": "Today", "why": "boost soil health"},
    {"step": 2, "action": "Spray neem oil on affected leaves", "when": "in 3 days", "why": "control pests"},
    {"step": 3, "action": "Intercrop with pigeon pea", "when": "Next planting season", "why": "fix nitrogen"},
]


def test_plan_to_tasks_dates_and_kinds():
    tasks = flows.plan_to_tasks(STEPS)
    assert len(tasks) == 3
    assert tasks[0]["kind"] == "nutrition" and tasks[0]["due_on"] == TODAY.isoformat()
    assert tasks[1]["kind"] == "spray" and tasks[1]["due_on"] == (TODAY + timedelta(days=3)).isoformat()
    assert tasks[2]["kind"] == "sowing" and tasks[2]["due_on"] is None  # seasonal -> undated
    # cycle_id is applied at insert time (add_tasks(farm_id, None, ...)), not here.
    assert all(t["source"] == "consult" for t in tasks)


def test_when_label_preserved_in_detail():
    """Fuzzy timing must survive even when undated."""
    t = flows.plan_to_tasks([{"action": "Mulch base", "when": "Next planting season", "why": "moisture"}])[0]
    assert "Next planting season" in t["detail"]


def test_empty_and_malformed_steps_dropped():
    tasks = flows.plan_to_tasks([{"action": ""}, "not a dict", {"why": "no action"}, None])
    assert tasks == []


# ---------- endpoint ----------
def test_add_plan_requires_auth(client):
    assert client.post("/api/planner/plan", json={"interaction_id": 1}).status_code == 401


def test_delete_task_requires_auth(client):
    assert client.delete("/api/calendar/tasks/1").status_code == 401


@pytest.mark.asyncio
async def test_add_plan_rejects_blocked_interaction(monkeypatch):
    """A safety-blocked answer must never convert into tasks."""
    from app.api import routes

    async def get_interaction(farm_id, iid):
        return {"id": iid, "kind": "consult", "blocked": True, "payload": {"action_plan": [{"action": "x", "when": "today"}]}}

    monkeypatch.setattr(routes.memory, "get_interaction", get_interaction)
    with pytest.raises(routes.HTTPException) as e:
        await routes.add_plan_to_planner(routes.AddPlanRequest(interaction_id=5), farm_id="f1")
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_add_plan_converts_a_real_consult(monkeypatch):
    from app.api import routes

    added: dict = {}

    async def get_interaction(farm_id, iid):
        return {"id": iid, "kind": "consult", "blocked": False,
                "payload": {"action_plan": [{"action": "Spray neem", "when": "today", "why": "pests"}]}}

    async def add_tasks(farm_id, cycle_id, tasks):
        added["cycle_id"] = cycle_id
        added["tasks"] = tasks
        return tasks

    monkeypatch.setattr(routes.memory, "get_interaction", get_interaction)
    monkeypatch.setattr(routes.memory, "add_tasks", add_tasks)
    monkeypatch.setattr(routes.flows, "invalidate_dashboard", lambda f: None)

    out = await routes.add_plan_to_planner(routes.AddPlanRequest(interaction_id=5), farm_id="f1")
    assert added["cycle_id"] is None, "consult tasks must be cycle-less"
    assert out["tasks"][0]["kind"] == "spray"


@pytest.mark.asyncio
async def test_add_plan_404_for_diagnose_interaction(monkeypatch):
    from app.api import routes

    async def get_interaction(farm_id, iid):
        return {"id": iid, "kind": "diagnose", "blocked": False, "payload": {}}

    monkeypatch.setattr(routes.memory, "get_interaction", get_interaction)
    with pytest.raises(routes.HTTPException) as e:
        await routes.add_plan_to_planner(routes.AddPlanRequest(interaction_id=5), farm_id="f1")
    assert e.value.status_code == 404
