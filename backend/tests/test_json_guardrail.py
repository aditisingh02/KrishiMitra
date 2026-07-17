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


# ---- vision path ----
# The diagnose path calls vision(), NOT chat_json(), so it needs its own retry.
# Without it a truncated reply is an unrecoverable failure after a slow, paid call.
IMG = "data:image/jpeg;base64,AAAA"


@pytest.mark.asyncio
async def test_vision_retries_once_then_succeeds(monkeypatch):
    calls: list[dict] = []

    async def fake_chat(messages, **kwargs):
        calls.append(kwargs)
        return "reasoning ran long and got cut" if len(calls) == 1 else '{"issue": "Early Blight"}'

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    out = await fw.fireworks.vision("prompt", IMG, system="sys")
    assert out == {"issue": "Early Blight"}
    assert len(calls) == 2, "vision must retry once on parse failure"
    # Truncation is the usual cause, so the retry needs more room, not just a resample.
    assert calls[1]["max_tokens"] > calls[0]["max_tokens"]
    assert calls[1]["temperature"] <= calls[0]["temperature"]


@pytest.mark.asyncio
async def test_vision_retries_at_most_once(monkeypatch):
    calls = []

    async def fake_chat(messages, **kwargs):
        calls.append(1)
        return "still not json"

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    out = await fw.fireworks.vision("prompt", IMG, system="sys")
    assert out["_parse_error"] is True
    assert len(calls) == 2, "a second image upload is expensive - cap the retry at one"


@pytest.mark.asyncio
async def test_vision_does_not_retry_on_success(monkeypatch):
    calls = []

    async def fake_chat(messages, **kwargs):
        calls.append(1)
        return '{"issue": "Powdery Mildew"}'

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    await fw.fireworks.vision("prompt", IMG, system="sys")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_vision_json_hardening_added_to_system_prompt(monkeypatch):
    seen: list[list[dict]] = []

    async def fake_chat(messages, **kwargs):
        seen.append(messages)
        return '{"ok": 1}'

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    await fw.fireworks.vision("prompt", IMG, system="You are the vision agent.")
    assert "valid JSON object" in seen[0][0]["content"]


@pytest.mark.asyncio
async def test_vision_sends_the_image_on_the_retry(monkeypatch):
    """The retry must carry the image - a text-only retry can't diagnose."""
    seen: list[list[dict]] = []

    async def fake_chat(messages, **kwargs):
        seen.append(messages)
        return "nope" if len(seen) == 1 else '{"issue": "x"}'

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    await fw.fireworks.vision("prompt", IMG, system="sys")
    retry_content = seen[1][-1]["content"]
    assert any(p.get("type") == "image_url" for p in retry_content)


@pytest.mark.asyncio
async def test_vision_non_json_mode_returns_raw_text(monkeypatch):
    async def fake_chat(messages, **kwargs):
        return "a plain sentence"

    monkeypatch.setattr(fw.fireworks, "chat", fake_chat)
    out = await fw.fireworks.vision("prompt", IMG, system="sys", json_mode=False)
    assert out == "a plain sentence"
