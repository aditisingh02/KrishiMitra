"""Rate limiting - the counters must actually block, and per-key not globally.

Each test uses a unique limiter key, so tests are independent without needing to
reset the shared in-memory storage between them.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from limits import parse

from app.core import limits


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(limits.settings, "rate_limit_enabled", True)


async def _hit(scope: str, key: str, limit: str = "3/minute") -> bool:
    """True if allowed, False if the limiter raised 429."""
    try:
        await limits._check(parse(limit), scope, key)
        return True
    except HTTPException as e:
        assert e.status_code == 429
        return False


@pytest.mark.asyncio
async def test_allows_up_to_the_limit_then_blocks():
    key = "user:limit_then_block"
    assert [await _hit("consult", key) for _ in range(3)] == [True, True, True]
    assert await _hit("consult", key) is False


@pytest.mark.asyncio
async def test_limits_are_per_user():
    """One user exhausting their quota must not affect another."""
    for _ in range(3):
        await _hit("consult", "user:per_user_a")
    assert await _hit("consult", "user:per_user_a") is False
    assert await _hit("consult", "user:per_user_b") is True


@pytest.mark.asyncio
async def test_limits_are_per_scope():
    """Spending the consult quota must not block diagnose."""
    key = "user:per_scope"
    for _ in range(3):
        await _hit("consult", key)
    assert await _hit("consult", key) is False
    assert await _hit("diagnose", key) is True


@pytest.mark.asyncio
async def test_429_carries_retry_after():
    key = "user:retry_after"
    for _ in range(3):
        await _hit("consult", key)
    with pytest.raises(HTTPException) as e:
        await limits._check(parse("3/minute"), "consult", key)
    assert e.value.status_code == 429
    retry_after = int(e.value.headers["Retry-After"])
    # Must be a sane wait, not an epoch timestamp.
    assert 1 <= retry_after <= 60


@pytest.mark.asyncio
async def test_disabled_limiter_never_blocks(monkeypatch):
    monkeypatch.setattr(limits.settings, "rate_limit_enabled", False)
    assert all([await _hit("consult", "user:disabled") for _ in range(50)])


def test_client_ip_prefers_forwarded_header():
    class Req:
        headers = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}
        client = type("C", (), {"host": "10.0.0.1"})()

    assert limits.client_ip(Req()) == "203.0.113.9"


def test_client_ip_falls_back_to_peer():
    class Req:
        headers: dict[str, str] = {}
        client = type("C", (), {"host": "198.51.100.7"})()

    assert limits.client_ip(Req()) == "198.51.100.7"
