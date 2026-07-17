"""Sentry wiring and agent metrics."""
from __future__ import annotations

import asyncio

import pytest

from app.core import observability as obs
from app.core.observability import AgentMetrics, _scrub, init_sentry, tracked


@pytest.fixture(autouse=True)
def _clean():
    obs.metrics.reset()
    yield
    obs.metrics.reset()


# ---------- metrics ----------
def test_records_calls_and_average_latency():
    m = AgentMetrics()
    m.record("crop_health", 100.0)
    m.record("crop_health", 200.0)
    snap = m.snapshot()["crop_health"]
    assert snap["calls"] == 2
    assert snap["avg_ms"] == 150.0
    assert snap["failures"] == 0


def test_records_failures_separately():
    m = AgentMetrics()
    m.record("market", 10.0, failed=True)
    m.record("market", 10.0)
    snap = m.snapshot()["market"]
    assert snap["calls"] == 2 and snap["failures"] == 1


def test_snapshot_is_empty_before_any_call():
    assert AgentMetrics().snapshot() == {}


def test_reset_clears():
    m = AgentMetrics()
    m.record("a", 1.0)
    m.reset()
    assert m.snapshot() == {}


# ---------- the async decorator trap ----------
@pytest.mark.asyncio
async def test_tracked_times_the_await_not_the_coroutine_creation():
    """@contextmanager is a ContextDecorator, so decorating an async def with
    `track()` would time only coroutine *creation* - ~0ms, silently wrong.
    `tracked()` must time the actual await."""

    @tracked("slow_agent")
    async def slow():
        await asyncio.sleep(0.05)
        return "done"

    assert await slow() == "done"
    snap = obs.metrics.snapshot()["slow_agent"]
    assert snap["calls"] == 1
    assert snap["avg_ms"] >= 40, f"timed {snap['avg_ms']}ms - decorator isn't awaiting inside the timer"


@pytest.mark.asyncio
async def test_tracked_records_failure_and_reraises():
    @tracked("boom_agent")
    async def boom():
        raise ValueError("upstream down")

    with pytest.raises(ValueError):
        await boom()
    snap = obs.metrics.snapshot()["boom_agent"]
    assert snap["calls"] == 1 and snap["failures"] == 1


@pytest.mark.asyncio
async def test_tracked_preserves_signature_and_return():
    @tracked("echo")
    async def echo(a, b=2):
        return a + b

    assert await echo(1, b=5) == 6
    assert echo.__name__ == "echo"


# ---------- Sentry ----------
def test_init_is_noop_without_dsn(monkeypatch):
    monkeypatch.setattr(obs.settings, "sentry_dsn", "")
    init_sentry()  # must not raise
    assert obs._sentry_ready is False


def test_scrub_removes_request_body():
    event = _scrub({"request": {"data": {"query": "my tomato leaves are yellow"}}}, {})
    assert event["request"]["data"] == "[scrubbed]"


def test_scrub_removes_auth_headers():
    event = _scrub(
        {"request": {"headers": {"Authorization": "Bearer secret", "X-Twilio-Signature": "sig", "Accept": "*/*"}}},
        {},
    )
    headers = event["request"]["headers"]
    assert "Authorization" not in headers
    assert "X-Twilio-Signature" not in headers
    assert "Accept" in headers  # harmless headers survive


def test_scrub_removes_farmer_content_from_extra():
    """A farmer's question and photo must never reach a third party."""
    event = _scrub(
        {"extra": {"image_data_url": "data:image/jpeg;base64,AAAA", "query": "private", "model": "kimi"}},
        {},
    )
    assert "image_data_url" not in event["extra"]
    assert "query" not in event["extra"]
    assert event["extra"]["model"] == "kimi"  # non-sensitive context survives


def test_scrub_removes_cookies():
    event = _scrub({"request": {"cookies": {"session": "abc"}}}, {})
    assert "cookies" not in event["request"]


def test_capture_without_sentry_does_not_raise(monkeypatch):
    monkeypatch.setattr(obs, "_sentry_ready", False)
    obs.capture(ValueError("x"), agent="market")  # logs only
