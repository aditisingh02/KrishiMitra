"""Thin async client around the Fireworks OpenAI-compatible API.

All agents share this client. It supports plain chat, JSON-mode chat (for
structured agent outputs) and multimodal vision chat (image + text).

**Connection reuse.** The underlying `httpx.AsyncClient` is created once and held
open, so calls reuse a warm TLS connection instead of paying a DNS+TCP+TLS
handshake (~100-300ms) every time. It's built lazily / on app startup rather than
at import, because a client constructed at import binds to whichever event loop
happens to exist then - which breaks under pytest and the monitor's background loop.

**Instrumentation.** Every call logs latency plus the provider's `usage` block
(prompt / completion / reasoning tokens). On a vision call `prompt_tokens` *is*
the image-token cost, which is how we measure whether image downscaling actually
helped rather than assuming it did.
"""
from __future__ import annotations

import json
import logging
import time
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
        self._client: httpx.AsyncClient | None = None

    # ---------- connection lifecycle ----------
    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            timeout=httpx.Timeout(120.0),  # per-call timeouts override this on .post()
        )

    async def startup(self) -> None:
        """Open the shared client. Called from the app lifespan."""
        if self._client is None or self._client.is_closed:
            self._client = self._new_client()

    async def aclose(self) -> None:
        """Close the shared client. Called from the app lifespan."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _get(self) -> httpx.AsyncClient:
        """The shared client, built on demand.

        Lazy fallback matters: tests build the app without running lifespan, and
        `monitor.loop()` runs outside any request.
        """
        if self._client is None or self._client.is_closed:
            self._client = self._new_client()
        return self._client

    @staticmethod
    def _log_usage(model: str, elapsed_ms: float, req_bytes: int, data: dict[str, Any]) -> None:
        """One structured line per call - the basis for any latency work."""
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        finish = (data.get("choices") or [{}])[0].get("finish_reason")
        logger.info(
            "fireworks call model=%s ms=%.0f req_kb=%.1f prompt_tokens=%s "
            "completion_tokens=%s reasoning_tokens=%s finish=%s",
            model,
            elapsed_ms,
            req_bytes / 1024,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            details.get("reasoning_tokens"),
            finish,
        )

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

        body = json.dumps(payload)
        started = time.perf_counter()
        resp = await self._get().post(
            f"{self._base}/chat/completions",
            content=body,
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        if resp.status_code != 200:
            logger.error(
                "Fireworks error %s after %.0fms: %s",
                resp.status_code, elapsed_ms, resp.text[:500],
            )
            raise FireworksError(f"Fireworks {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        self._log_usage(payload["model"], elapsed_ms, len(body), data)
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
        started = time.perf_counter()
        resp = await self._get().post(
            f"{self._base}/embeddings",
            json=payload,
            timeout=60.0,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if resp.status_code != 200:
            logger.error("Fireworks embed error %s: %s", resp.status_code, resp.text[:500])
            raise FireworksError(f"Fireworks embed {resp.status_code}: {resp.text[:200]}")
        logger.info("fireworks embed ms=%.0f chars=%d", elapsed_ms, len(text))
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
        retry_on_parse_error: bool = True,
    ) -> dict[str, Any] | str:
        """Multimodal call: text prompt + one image (data URL or http URL).

        Gets the same single parse-retry as `chat_json`. It matters more here, not
        less: the vision model reasons heavily before emitting content, so a
        truncated reply (`finish_reason=length`) is the likeliest failure - and
        without a retry the farmer waits through a slow diagnosis only to get
        nothing back.

        The retry costs a second image upload and prefill, which is why it's
        capped at one and why we raise the token budget rather than resample at
        the same settings: repeating an identical call that ran out of room would
        just run out of room again.
        """
        sys_prompt = system
        if json_mode and sys_prompt:
            sys_prompt += (
                "\n\nReply ONLY with a valid JSON object. Fill every field with real "
                "values - never use placeholders like '...' or 'string'."
            )

        def build(extra: str = "") -> list[dict[str, Any]]:
            msgs: list[dict[str, Any]] = []
            if sys_prompt:
                msgs.append({"role": "system", "content": sys_prompt + extra})
            msgs.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            )
            return msgs

        content = await self.chat(
            build(),
            model=model or settings.model_vision,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        if not json_mode:
            return content

        result = _safe_json(content)
        if not result.get("_parse_error") or not retry_on_parse_error:
            return result

        logger.warning("vision JSON parse failed - retrying once (model=%s)", model or settings.model_vision)
        content = await self.chat(
            build("\n\nYour previous reply was not valid JSON. Return a single, complete, valid JSON object and nothing else."),
            model=model or settings.model_vision,
            temperature=min(temperature, 0.1),
            max_tokens=int(max_tokens * 1.5),  # the usual cause is truncation
            json_mode=json_mode,
        )
        retried = _safe_json(content)
        if retried.get("_parse_error"):
            logger.error("vision JSON parse failed after retry (model=%s)", model or settings.model_vision)
        return retried


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
