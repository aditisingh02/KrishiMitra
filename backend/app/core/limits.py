"""Rate limiting.

Every endpoint that spends money (LLM/vision calls) or does unbounded work is
throttled. Authenticated routes are keyed by Clerk user id so one user can't
exhaust the budget for everyone; public routes (i18n, the WhatsApp webhook) are
keyed by client IP.

Implemented as a FastAPI **dependency** rather than a decorator. slowapi's
decorator wraps the endpoint, which breaks FastAPI's resolution of `UploadFile`
annotations under `from __future__ import annotations` (they arrive as
unresolvable ForwardRefs). A dependency is signature-agnostic, composes with
`Depends(get_current_user)`, and lets us key on the *verified* user id: FastAPI
caches `get_current_user` per request, so the JWT is still only checked once.

Limits are configurable via settings so they can be relaxed in dev/tests.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from limits import RateLimitItem, parse
from limits.aio.storage import MemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
from limits.storage import storage_from_string

from app.core.auth import get_current_user
from app.core.config import settings

logger = logging.getLogger("krishimitra.limits")


def _build_storage():
    """In-memory is fine for one instance; point RATE_LIMIT_STORAGE_URI at Redis
    (redis://...) when running multiple workers so limits are shared.

    `limits` picks the async backend from an `async+` scheme prefix, which we add
    for the caller so the setting takes a plain `redis://` URL.
    """
    uri = settings.rate_limit_storage_uri
    if not uri:
        return MemoryStorage()
    if not uri.startswith("async+"):
        uri = f"async+{uri}"
    return storage_from_string(uri)


_storage = _build_storage()
_strategy = MovingWindowRateLimiter(_storage)


def client_ip(request: Request) -> str:
    """Client IP, honouring X-Forwarded-For when behind a proxy (Render/ngrok)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _check(item: RateLimitItem, scope: str, key: str) -> None:
    if not settings.rate_limit_enabled:
        return
    if await _strategy.hit(item, scope, key):
        return

    # `reset_time` is an absolute epoch timestamp - Retry-After is a delay in
    # seconds, so it has to be measured from now.
    window = await _strategy.get_window_stats(item, scope, key)
    retry_after = max(1, int(window.reset_time - time.time()))
    logger.info("rate limit hit: %s on %s (retry in %ss)", key, scope, retry_after)
    raise HTTPException(
        status_code=429,
        detail="Too many requests - please wait a moment and try again.",
        headers={"Retry-After": str(retry_after)},
    )


def user_rate_limit(limit_str: str, scope: str) -> Callable:
    """Dependency limiting an authenticated route, keyed by Clerk user id."""
    item = parse(limit_str)

    async def dependency(user: str = Depends(get_current_user)) -> None:
        await _check(item, scope, f"user:{user}")

    return dependency


def ip_rate_limit(limit_str: str, scope: str) -> Callable:
    """Dependency limiting a public route, keyed by client IP."""
    item = parse(limit_str)

    async def dependency(request: Request) -> None:
        await _check(item, scope, f"ip:{client_ip(request)}")

    return dependency
