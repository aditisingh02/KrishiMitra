"""Shared outbound HTTP client for third-party APIs (OpenWeather, Agmarknet).

One pooled `httpx.AsyncClient` instead of building a new one per call. A fresh
client means a fresh DNS+TCP+TLS handshake every time (~100-300ms); keeping
connections warm removes that from every forecast and mandi-price fetch, several
of which sit directly in the dashboard's latency budget.

Built lazily / on app startup rather than at import: a client constructed at
import time binds to whatever event loop exists then, which breaks under pytest
and in the monitor's background task.

Fireworks has its own client (app/core/fireworks.py) because it carries auth
headers and a much longer timeout.
"""
from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def _new() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=30),
        timeout=httpx.Timeout(20.0),  # per-call timeouts override on the request
    )


def get_client() -> httpx.AsyncClient:
    """The shared client, built on demand."""
    global _client
    if _client is None or _client.is_closed:
        _client = _new()
    return _client


async def startup() -> None:
    get_client()


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
