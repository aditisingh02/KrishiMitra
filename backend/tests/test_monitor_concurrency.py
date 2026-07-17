"""Monitor concurrency (P1 item 11).

The cycle used to await each farm in turn. Each farm costs an LLM risk agent plus
weather/market fetches (~10s), so 500 farms ≈ 90 minutes and growing linearly -
eventually a daily cycle can't finish inside a day.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import monitor


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(monitor.settings, "monitor_concurrency", 8)
    # A cycle runs risk alerts AND calendar reminders per farm. These tests are
    # about the risk-alert fan-out, so stub the calendar (it would otherwise reach
    # for a database that isn't running here). Calendar reminders have their own
    # tests in test_calendar.py.
    async def no_calendar(farm):
        return 0

    monkeypatch.setattr(monitor, "check_calendar", no_calendar)


def _farms(n: int) -> list[dict]:
    return [{"id": f"farm_{i}", "farmer": f"F{i}"} for i in range(n)]


@pytest.mark.asyncio
async def test_farms_are_checked_concurrently(monkeypatch):
    """20 farms x 50ms serially would be ~1s; concurrently it should be far less."""
    monkeypatch.setattr(monitor.memory, "all_farms", lambda: _async(_farms(20)))

    async def slow_check(farm):
        await asyncio.sleep(0.05)
        return 1

    monkeypatch.setattr(monitor, "check_farm", slow_check)

    started = asyncio.get_event_loop().time()
    result = await monitor.run_once()
    elapsed = asyncio.get_event_loop().time() - started

    assert result["farms_checked"] == 20
    assert result["alerts_created"] == 20
    assert elapsed < 0.5, f"took {elapsed:.2f}s - farms are still serial"


@pytest.mark.asyncio
async def test_concurrency_is_bounded(monkeypatch):
    """Unbounded gather would fire every farm's LLM call at once and trip
    provider rate limits. The semaphore must cap in-flight work."""
    monkeypatch.setattr(monitor.settings, "monitor_concurrency", 4)
    monkeypatch.setattr(monitor.memory, "all_farms", lambda: _async(_farms(30)))

    in_flight = 0
    peak = 0

    async def tracking_check(farm):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return 0

    monkeypatch.setattr(monitor, "check_farm", tracking_check)
    await monitor.run_once()
    assert peak <= 4, f"peak concurrency {peak} exceeded the configured limit of 4"


@pytest.mark.asyncio
async def test_one_bad_farm_does_not_abort_the_cycle(monkeypatch):
    monkeypatch.setattr(monitor.memory, "all_farms", lambda: _async(_farms(5)))

    async def flaky(farm):
        if farm["id"] == "farm_2":
            raise RuntimeError("boom")
        return 1

    monkeypatch.setattr(monitor, "check_farm", flaky)
    result = await monitor.run_once()
    assert result["farms_checked"] == 5
    assert result["alerts_created"] == 4  # the other four still ran
    assert result["farms_failed"] == 1


@pytest.mark.asyncio
async def test_no_farms_is_a_clean_noop(monkeypatch):
    monkeypatch.setattr(monitor.memory, "all_farms", lambda: _async([]))
    assert await monitor.run_once() == {"farms_checked": 0, "alerts_created": 0}


@pytest.mark.asyncio
async def test_concurrency_of_one_still_works(monkeypatch):
    """Config guard: 0 or negative must not deadlock (max(1, ...))."""
    monkeypatch.setattr(monitor.settings, "monitor_concurrency", 0)
    monkeypatch.setattr(monitor.memory, "all_farms", lambda: _async(_farms(3)))

    async def check(farm):
        return 1

    monkeypatch.setattr(monitor, "check_farm", check)
    result = await monitor.run_once()
    assert result["alerts_created"] == 3


def _async(value):
    async def inner():
        return value

    return inner()
