"""Thin async client around the Fireworks OpenAI-compatible API.

All agents share this client. It supports plain chat, JSON-mode chat (for
structured agent outputs) and multimodal vision chat (image + text).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("krishimitra.fireworks")


class FireworksError(RuntimeError):
    pass


class FireworksClient:
    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {settings.fireworks_api_key}",
            "Content-Type": "application/json",
        }
        self._base = settings.fireworks_base_url

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        json_mode: bool = False,
        reasoning_effort: str | None = "low",
        timeout: float = 120.0,
    ) -> str:
        """Return the assistant message content for a chat completion.

        Reasoning models (gpt-oss, kimi) emit a separate `reasoning_content`.
        We only return `content`. `reasoning_effort` keeps that overhead small on
        models that honour it (gpt-oss); models that ignore it (kimi) just need a
        large `max_tokens` so the JSON content isn't starved by the reasoning.
        """
        payload: dict[str, Any] = {
            "model": model or settings.model_agent,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self._base}/chat/completions",
                headers=self._headers,
                json=payload,
            )
        if resp.status_code != 200:
            logger.error("Fireworks error %s: %s", resp.status_code, resp.text[:500])
            raise FireworksError(f"Fireworks {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        if not content.strip() and choice.get("finish_reason") == "length":
            logger.warning("Empty content with finish_reason=length - raise max_tokens")
        return content

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        reasoning_effort: str | None = "low",
        retry_on_parse_error: bool = True,
    ) -> dict[str, Any]:
        """Chat that is expected to return a JSON object. Robust to fences.

        On an unparseable response we retry exactly once with a lower temperature
        and a larger token budget - the two causes we actually see are sampling
        noise and truncation (`finish_reason=length` starving the JSON). If the
        retry also fails we return `{_raw, _parse_error}` and the caller degrades
        gracefully rather than showing the farmer a broken section.
        """
        prompt = system + (
            "\n\nReply ONLY with a valid JSON object. Fill every field with real "
            "values - never use placeholders like '...' or 'string'."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ]
        content = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            reasoning_effort=reasoning_effort,
        )
        result = _safe_json(content)
        if not result.get("_parse_error") or not retry_on_parse_error:
            return result

        logger.warning("JSON parse failed - retrying once (model=%s)", model or settings.model_agent)
        retry_messages = [
            {"role": "system", "content": prompt + "\n\nYour previous reply was not valid JSON. Return a single, complete, valid JSON object and nothing else."},
            {"role": "user", "content": user},
        ]
        content = await self.chat(
            retry_messages,
            model=model,
            temperature=min(temperature, 0.1),
            max_tokens=int(max_tokens * 1.5),
            json_mode=True,
            reasoning_effort=reasoning_effort,
        )
        retried = _safe_json(content)
        if retried.get("_parse_error"):
            logger.error("JSON parse failed after retry (model=%s)", model or settings.model_agent)
        return retried

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """Return an embedding vector for `text` (OpenAI-compatible /embeddings).

        Powers the pgvector long-term memory. The returned vector length must match
        `settings.embed_dim`; if you change the embedding model, update that too.
        """
        payload = {"model": model or settings.model_embed, "input": text}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base}/embeddings",
                headers=self._headers,
                json=payload,
            )
        if resp.status_code != 200:
            logger.error("Fireworks embed error %s: %s", resp.status_code, resp.text[:500])
            raise FireworksError(f"Fireworks embed {resp.status_code}: {resp.text[:200]}")
        return resp.json()["data"][0]["embedding"]

    async def vision(
        self,
        prompt: str,
        image_data_url: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        json_mode: bool = True,
    ) -> dict[str, Any] | str:
        """Multimodal call: text prompt + one image (data URL or http URL)."""
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        )
        content = await self.chat(
            messages,
            model=model or settings.model_vision,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        return _safe_json(content) if json_mode else content


def _safe_json(text: str) -> dict[str, Any]:
    """Parse JSON that may be wrapped in markdown fences or have prose around it."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning("Could not parse JSON from model output: %s", text[:300])
    return {"_raw": text, "_parse_error": True}


fireworks = FireworksClient()
