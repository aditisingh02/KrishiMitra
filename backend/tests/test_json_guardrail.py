"""JSON output validation: parsing, and the single automatic retry."""
from __future__ import annotations

import pytest

from app.core import fireworks as fw
from app.core.fireworks import _safe_json


def test_parses_plain_json():
    assert _safe_json('{"level": "high"}') == {"level": "high"}


def test_parses_fenced_json():
    assert _safe_json('```json\n{"level": "high"}\n```') == {"level": "high"}
    assert _safe_json('```\n{"level": "high"}\n```') == {"level": "high"}


def test_parses_json_with_surrounding_prose():
    out = _safe_json('Here you go:\n{"level": "high"}\nHope that helps!')
    assert out == {"level": "high"}


def test_unparseable_flags_parse_error():
    out = _safe_json("I could not answer that.")
    assert out["_parse_error"] is True
    assert out["_raw"] == "I could not answer that."


def test_empty_flags_parse_error():
    assert _safe_json("")["_parse_error"] is True


def test_nested_json_survives():
    out = _safe_json('{"a": {"b": [1, 2]}, "c": "x"}')
    assert out["a"]["b"] == [1, 2]


@pytest.mark.asyncio
async def test_chat_json_retries_once_then_succeeds(monkeypatch):
    """First reply is garbage, retry returns valid JSON -> caller sees the JSON."""
    calls: list[dict] = []

    async def fake_chat(messages, **kwargs):
        calls.append(kwargs)
        return "not json at all" if len(calls) == 1 else '{"ok": true}'

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    out = await fw.fireworks.chat_json("sys", "user")
    assert out == {"ok": True}
    assert len(calls) == 2, "expected exactly one retry"
    # retry should be more conservative
    assert calls[1]["temperature"] <= calls[0]["temperature"]
    assert calls[1]["max_tokens"] > calls[0]["max_tokens"]


@pytest.mark.asyncio
async def test_chat_json_retries_at_most_once(monkeypatch):
    """Two failures -> parse error surfaced, not an infinite retry loop."""
    calls = []

    async def fake_chat(messages, **kwargs):
        calls.append(1)
        return "still not json"

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    out = await fw.fireworks.chat_json("sys", "user")
    assert out["_parse_error"] is True
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_chat_json_no_retry_when_disabled(monkeypatch):
    calls = []

    async def fake_chat(messages, **kwargs):
        calls.append(1)
        return "nope"

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    out = await fw.fireworks.chat_json("sys", "user", retry_on_parse_error=False)
    assert out["_parse_error"] is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_chat_json_does_not_retry_on_success(monkeypatch):
    calls = []

    async def fake_chat(messages, **kwargs):
        calls.append(1)
        return '{"ok": 1}'

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    await fw.fireworks.chat_json("sys", "user")
    assert len(calls) == 1
