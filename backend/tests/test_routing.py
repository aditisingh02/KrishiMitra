"""Request routing: the planner's task graph must be filtered to real agents."""
from __future__ import annotations

import pytest

from app.agents import orchestrator


@pytest.mark.asyncio
async def test_invalid_tasks_are_filtered(monkeypatch):
    async def fake_chat_json(system, user, **kwargs):
        return {"intent": "x", "tasks": ["crop_health", "delete_everything", "market"]}

    monkeypatch.setattr(orchestrator.fireworks, "chat_json", fake_chat_json)
    plan = await orchestrator.plan_tasks("q", "ctx")
    assert plan["tasks"] == ["crop_health", "market"]


@pytest.mark.asyncio
async def test_empty_task_list_falls_back_to_safe_default(monkeypatch):
    async def fake_chat_json(system, user, **kwargs):
        return {"tasks": []}

    monkeypatch.setattr(orchestrator.fireworks, "chat_json", fake_chat_json)
    plan = await orchestrator.plan_tasks("q", "ctx")
    assert plan["tasks"] == ["crop_health", "natural_farming"]


@pytest.mark.asyncio
async def test_all_invalid_tasks_falls_back(monkeypatch):
    async def fake_chat_json(system, user, **kwargs):
        return {"tasks": ["rm -rf", "exfiltrate"]}

    monkeypatch.setattr(orchestrator.fireworks, "chat_json", fake_chat_json)
    plan = await orchestrator.plan_tasks("q", "ctx")
    assert plan["tasks"] == ["crop_health", "natural_farming"]


@pytest.mark.asyncio
async def test_parse_error_plan_falls_back(monkeypatch):
    """An unparseable planner reply must not crash the consult."""

    async def fake_chat_json(system, user, **kwargs):
        return {"_raw": "junk", "_parse_error": True}

    monkeypatch.setattr(orchestrator.fireworks, "chat_json", fake_chat_json)
    plan = await orchestrator.plan_tasks("q", "ctx")
    assert plan["tasks"] == ["crop_health", "natural_farming"]


@pytest.mark.asyncio
async def test_planner_flags_off_topic(monkeypatch):
    """A non-farm question the planner marks off_topic → no default tasks."""

    async def fake_chat_json(system, user, **kwargs):
        return {"on_topic": False, "tasks": []}

    monkeypatch.setattr(orchestrator.fireworks, "chat_json", fake_chat_json)
    plan = await orchestrator.plan_tasks("who won the cricket match?", "ctx")
    assert plan["on_topic"] is False
    assert plan["tasks"] == [], "off-topic must NOT get the crop_health default"


@pytest.mark.asyncio
async def test_missing_on_topic_defaults_true(monkeypatch):
    """A parse hiccup must never wrongly reject a real farm question."""

    async def fake_chat_json(system, user, **kwargs):
        return {"tasks": ["market"]}  # no on_topic field

    monkeypatch.setattr(orchestrator.fireworks, "chat_json", fake_chat_json)
    plan = await orchestrator.plan_tasks("sell my onions?", "ctx")
    assert plan["on_topic"] is True


@pytest.mark.asyncio
async def test_valid_tasks_preserved(monkeypatch):
    async def fake_chat_json(system, user, **kwargs):
        return {"tasks": sorted(orchestrator.VALID_TASKS)}

    monkeypatch.setattr(orchestrator.fireworks, "chat_json", fake_chat_json)
    plan = await orchestrator.plan_tasks("q", "ctx")
    assert set(plan["tasks"]) == orchestrator.VALID_TASKS
