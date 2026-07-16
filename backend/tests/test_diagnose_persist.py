"""Post-response persistence for diagnoses.

The latency win is that record_disease + the embedding round-trip happen AFTER the
farmer has their answer. That's only safe if the ordering and error handling hold,
which is what these lock down.
"""
from __future__ import annotations

import pytest

from app.agents import flows


# ---------- needs_persisting ----------
def test_real_issue_is_persisted():
    assert flows.needs_persisting({"issue": "Early Blight", "category": "disease"})


@pytest.mark.parametrize(
    "payload",
    [
        {"issue": "", "category": "disease"},              # nothing found
        {"category": "disease"},                            # no issue key
        {"issue": "Healthy", "category": "healthy"},        # healthy plant
        {"issue": "X", "_parse_error": True},               # unusable model output
        "not a dict",
        {},
    ],
)
def test_non_issues_are_not_persisted(payload):
    assert not flows.needs_persisting(payload)


# ---------- persist_diagnosis ----------
@pytest.fixture
def spy(monkeypatch):
    """Record call order across the persist steps."""
    calls: list[str] = []

    async def record_disease(issue, crop, farm_id):
        calls.append("record_disease")

    async def add_memory(farm_id, kind, text, meta=None):
        calls.append("add_memory")

    def invalidate(farm_id):
        calls.append("invalidate")

    monkeypatch.setattr(flows.memory, "record_disease", record_disease)
    monkeypatch.setattr(flows.memory, "add_memory", add_memory)
    monkeypatch.setattr(flows, "invalidate_dashboard", invalidate)
    return calls


DIAG = {"issue": "Early Blight", "category": "disease", "crop_guess": "tomato", "severity": "high"}


@pytest.mark.asyncio
async def test_invalidate_happens_after_the_write(spy):
    """The race that matters.

    If the dashboard cache is dropped before record_disease commits, a concurrent
    dashboard load rebuilds from farm data WITHOUT the new disease and re-caches
    that stale view for the full TTL. Invalidation must come last.
    """
    await flows.persist_diagnosis(DIAG, "farm_1")
    assert spy == ["record_disease", "add_memory", "invalidate"]
    assert spy.index("invalidate") > spy.index("record_disease")


@pytest.mark.asyncio
async def test_failure_is_contained_and_does_not_raise(monkeypatch):
    """This runs after the response is sent - raising would help nobody."""

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(flows.memory, "record_disease", boom)
    await flows.persist_diagnosis(DIAG, "farm_1")  # must not raise


@pytest.mark.asyncio
async def test_embed_failure_does_not_block_invalidate_silently(monkeypatch, caplog):
    """If add_memory dies the error must be logged, not swallowed invisibly."""

    async def ok(*a, **k):
        return None

    async def boom(*a, **k):
        raise RuntimeError("embedding service down")

    monkeypatch.setattr(flows.memory, "record_disease", ok)
    monkeypatch.setattr(flows.memory, "add_memory", boom)
    with caplog.at_level("ERROR"):
        await flows.persist_diagnosis(DIAG, "farm_1")
    assert any("persist failed" in r.message for r in caplog.records)


# ---------- context_blob passthrough (duplicate-read fix) ----------
@pytest.mark.asyncio
async def test_context_blob_uses_supplied_farm(monkeypatch):
    """Passing the farm must skip the redundant re-query."""
    from app.services.memory import memory

    fetches = []

    async def get_farm(farm_id):
        fetches.append(farm_id)
        return {"id": farm_id, "farmer": "refetched"}

    async def recent_events(n, farm_id):
        return []

    monkeypatch.setattr(memory, "get_farm", get_farm)
    monkeypatch.setattr(memory, "recent_events", recent_events)

    blob = await memory.context_blob("farm_1", farm={"id": "farm_1", "farmer": "supplied"})
    assert fetches == [], "context_blob re-queried a farm it was handed"
    assert "supplied" in blob


@pytest.mark.asyncio
async def test_context_blob_still_fetches_when_not_supplied(monkeypatch):
    """Back-compat: the old single-arg call must keep working."""
    from app.services.memory import memory

    fetches = []

    async def get_farm(farm_id):
        fetches.append(farm_id)
        return {"id": farm_id}

    async def recent_events(n, farm_id):
        return []

    monkeypatch.setattr(memory, "get_farm", get_farm)
    monkeypatch.setattr(memory, "recent_events", recent_events)

    await memory.context_blob("farm_1")
    assert fetches == ["farm_1"]
