"""Error tracking (Sentry) and agent-level metrics.

Two separate concerns, deliberately kept independent:

* **Sentry** - unhandled exceptions and slow transactions. Entirely optional: with
  no `SENTRY_DSN` set, `init_sentry()` is a no-op and the SDK is never imported at
  runtime cost. Nothing here may become load-bearing.
* **Agent metrics** - per-agent latency, failures and token spend. This is the
  system's real operating cost, and it's invisible in request logs because one
  farmer question fans out into a planner call plus N specialists.

**Privacy.** A farmer's question, their farm data and their photos must never
leave this system. `send_default_pii` stays off, and `_scrub` drops anything that
could carry a message body or an image before it's transmitted. An error report
is worth having; a farm's private data on a third-party server is not.
"""
from __future__ import annotations

import functools
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypeVar

from app.core.config import settings

logger = logging.getLogger("krishimitra.observability")

F = TypeVar("F", bound=Callable[..., Any])

_sentry_ready = False


# ---------- Sentry ----------
def _scrub(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Strip farmer content before anything leaves the process.

    Vision payloads are base64 images and consult payloads are the farmer's own
    words - neither belongs in an error tracker. We keep the shape of the error
    and drop the contents.
    """
    request = event.get("request") or {}
    if "data" in request:
        request["data"] = "[scrubbed]"
    if "cookies" in request:
        request.pop("cookies")
    headers = request.get("headers") or {}
    for h in ("Authorization", "authorization", "X-Twilio-Signature", "Cookie"):
        headers.pop(h, None)

    for key in ("extra", "contexts"):
        section = event.get(key) or {}
        for field in ("image_data_url", "query", "body", "note", "answer_local", "answer_en"):
            section.pop(field, None)
    return event


def init_sentry() -> None:
    """Initialise Sentry if a DSN is configured. Safe to call when it isn't."""
    global _sentry_ready
    if not settings.sentry_dsn:
        logger.info("SENTRY_DSN not set - error tracking disabled")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            release=settings.sentry_release or None,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            # Never attach request bodies, headers or user identifiers.
            send_default_pii=False,
            before_send=_scrub,
            integrations=[FastApiIntegration(), AsyncioIntegration()],
        )
        _sentry_ready = True
        logger.info("Sentry initialised (env=%s)", settings.sentry_environment)
    except Exception as e:  # noqa: BLE001 - observability must never break boot
        logger.warning("Sentry init failed (continuing without it): %s", e)


def capture(exc: BaseException, **tags: str) -> None:
    """Report an exception if Sentry is on; always log it either way."""
    logger.exception("captured exception: %s", exc)
    if not _sentry_ready:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for k, v in tags.items():
                scope.set_tag(k, v)
            sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        logger.debug("sentry capture failed", exc_info=True)


# ---------- agent metrics ----------
class AgentMetrics:
    """In-process counters for agent calls.

    Deliberately in-memory and per-worker: this is a health signal, not billing.
    Anything authoritative should come from Sentry or the provider's own usage
    dashboard. (Same caveat as the rate limiter - see config.py - a second worker
    keeps its own counters.)
    """

    def __init__(self) -> None:
        self.calls: dict[str, int] = defaultdict(int)
        self.failures: dict[str, int] = defaultdict(int)
        self.total_ms: dict[str, float] = defaultdict(float)
        self.tokens: dict[str, int] = defaultdict(int)

    def record(self, agent: str, ms: float, *, failed: bool = False, tokens: int = 0) -> None:
        self.calls[agent] += 1
        self.total_ms[agent] += ms
        self.tokens[agent] += tokens
        if failed:
            self.failures[agent] += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            agent: {
                "calls": n,
                "failures": self.failures[agent],
                "avg_ms": round(self.total_ms[agent] / n, 1) if n else 0,
                "tokens": self.tokens[agent],
            }
            for agent, n in sorted(self.calls.items())
        }

    def reset(self) -> None:
        self.calls.clear()
        self.failures.clear()
        self.total_ms.clear()
        self.tokens.clear()


metrics = AgentMetrics()


@contextmanager
def track(agent: str):
    """Time one agent call and record success/failure.

        with track("crop_health"):
            ...

    Re-raises: this measures, it never swallows.

    NOTE: do not use this as a decorator on an `async def`. A @contextmanager is a
    ContextDecorator, so it would happily decorate a coroutine function and time
    only the coroutine's *creation* - reporting ~0ms for every agent while looking
    perfectly correct. Use `tracked()` below for async.
    """
    started = time.perf_counter()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        metrics.record(agent, elapsed, failed=failed)
        logger.debug("agent %s took %.0fms (failed=%s)", agent, elapsed, failed)


def tracked(agent: str) -> Callable[[F], F]:
    """Decorator timing an async agent call - awaits inside the timer.

        @tracked("crop_health")
        async def _run_crop_health(...): ...
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            with track(agent):
                return await fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
