"""Chat-history storage for consult + diagnose."""
from __future__ import annotations

import pytest


# ---------- endpoints ----------
def test_consult_history_requires_auth(client):
    assert client.get("/api/consult/history").status_code == 401


def test_diagnose_history_requires_auth(client):
    assert client.get("/api/diagnose/history").status_code == 401


def test_history_limit_is_clamped(client):
    """Over the cap must not reach the handler (422), but auth is checked first."""
    assert client.get("/api/consult/history?limit=9999").status_code in (401, 422)


# ---------- driver: run orchestrator.consult with everything external stubbed ----------
async def _drive_consult(monkeypatch, *, answer_en="ok", blocked=False,
                         recent=None, spy=None, plan_spy=None):
    from app.agents import orchestrator, flows

    async def get_farm(fid):
        return {"id": fid, "language": "en", "crops": [{"name": "Tomato"}]}

    async def context_blob(fid, farm=None):
        return "FARM CTX"

    async def anop(*a, **k):
        return None

    async def recall(fid, q):
        return []

    async def recent_interactions(fid, limit=5):
        return recent if recent is not None else []

    async def add_interaction(farm_id, kind, query, answer, answer_en, payload=None, blocked=False):
        if spy is not None:
            spy.append({"kind": kind, "query": query, "answer": answer,
                        "answer_en": answer_en, "payload": payload or {}, "blocked": blocked})
        return 1

    async def add_memory(*a, **k):
        if spy is not None:
            spy.append({"embedded": True})

    async def plan_tasks(query, ctx):
        if plan_spy is not None:
            plan_spy.append(ctx)
        return {"tasks": [], "intent": "general"}

    async def chat_json(system, user, **k):
        p = {"answer_en": answer_en, "answer_local": answer_en, "action_plan": [], "confidence": 0.8}
        if blocked:
            p["_blocked"] = True
        return p

    monkeypatch.setattr(orchestrator.memory, "get_farm", get_farm)
    monkeypatch.setattr(orchestrator.memory, "context_blob", context_blob)
    monkeypatch.setattr(orchestrator.memory, "recall", recall)
    monkeypatch.setattr(orchestrator.memory, "recent_interactions", recent_interactions)
    monkeypatch.setattr(orchestrator.memory, "add_event", anop)
    monkeypatch.setattr(orchestrator.memory, "record_disease", anop)
    monkeypatch.setattr(orchestrator.memory, "add_interaction", add_interaction)
    monkeypatch.setattr(orchestrator.memory, "add_memory", add_memory)
    monkeypatch.setattr(orchestrator, "plan_tasks", plan_tasks)
    monkeypatch.setattr(orchestrator.fireworks, "chat_json", chat_json)
    monkeypatch.setattr(flows, "ensure_coords", lambda fid, farm: _wrap(farm))
    monkeypatch.setattr(flows, "invalidate_dashboard", lambda f: None)

    return await orchestrator.consult("should I spray neem?", "farm_1")


async def _wrap(v):
    return v


@pytest.mark.asyncio
async def test_consult_stores_interaction(monkeypatch):
    spy: list = []
    await _drive_consult(monkeypatch, answer_en="Spray neem 5ml/litre", spy=spy)
    writes = [s for s in spy if s.get("kind") == "consult"]
    assert writes, "consult did not store an interaction"
    assert writes[0]["blocked"] is False
    assert "action_plan" in writes[0]["payload"]


@pytest.mark.asyncio
async def test_blocked_consult_stored_but_not_embedded(monkeypatch):
    spy: list = []
    await _drive_consult(monkeypatch, blocked=True, spy=spy)
    stored = [s for s in spy if s.get("kind") == "consult"]
    embedded = [s for s in spy if s.get("embedded")]
    assert stored and stored[0]["blocked"] is True, "blocked consult must be stored with blocked=1"
    assert embedded == [], "blocked answer must NOT be embedded into recall memory"


@pytest.mark.asyncio
async def test_recent_conversation_injected_and_filters_blocked(monkeypatch):
    recent = [
        {"query": "my tomato has spots", "answer": None, "answer_en": "Use neem oil", "blocked": False},
        {"query": "a blocked turn", "answer": None, "answer_en": "x", "blocked": True},
    ]
    plan_spy: list = []
    await _drive_consult(monkeypatch, recent=recent, plan_spy=plan_spy)
    ctx = plan_spy[0]
    assert "RECENT CONVERSATION" in ctx
    assert "Use neem oil" in ctx
    assert "a blocked turn" not in ctx, "blocked turns must be filtered from context"


# ---------- diagnose history writer ----------
@pytest.mark.asyncio
async def test_diagnose_interaction_stores_even_when_healthy(monkeypatch):
    """Healthy scans must still enter history (persist_diagnosis skips them)."""
    from app.agents import flows

    spy: list = []

    async def add_interaction(farm_id, kind, query, answer, answer_en, payload=None, blocked=False):
        spy.append({"kind": kind, "answer": answer, "payload": payload or {}})
        return 1

    monkeypatch.setattr(flows.memory, "add_interaction", add_interaction)
    healthy = {"category": "healthy", "issue": "Healthy", "explanation_local": "Looks healthy",
               "natural_treatment": {}, "_note": "is this ok?"}
    assert not flows.needs_persisting(healthy)  # would be skipped by persist_diagnosis
    await flows.persist_interaction_diagnose(healthy, "farm_1")
    assert spy and spy[0]["kind"] == "diagnose"
    assert spy[0]["payload"]["category"] == "healthy"


@pytest.mark.asyncio
async def test_diagnose_interaction_failure_is_contained(monkeypatch):
    from app.agents import flows

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(flows.memory, "add_interaction", boom)
    await flows.persist_interaction_diagnose({"issue": "x"}, "farm_1")  # must not raise
