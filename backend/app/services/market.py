"""Market service - real mandi prices from data.gov.in (Agmarknet).

Resource: "Current Daily Price of Various Commodities from Various Markets".
Requires DATA_GOV_API_KEY. Raises ExternalDataError on missing key / failure.

Agmarknet has no price forecast, so we report only real values: latest modal
price and the change vs the earliest record we have for that commodity+market.

The upstream is free but flaky - usually ~0.5s, but it intermittently times out
completely. To keep the dashboard from blanking on a single slow call we (1) fetch
all crops concurrently, (2) retry each request once, and (3) keep a per-crop TTL
cache so a transient upstream failure falls back to the last good price.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

import httpx

from app.core import http
from app.core.config import settings
from app.services.weather import ExternalDataError

logger = logging.getLogger(__name__)

# Per-(crop, state) cache of summarized items. Mandi prices update once a day, so
# a fresh entry is reused for CACHE_TTL; on upstream failure we serve a stale entry
# regardless of age rather than show nothing.
CACHE_TTL = 60 * 60  # 1 hour
_cache: dict[tuple[str, str | None], tuple[float, dict[str, Any]]] = {}

# data.gov.in's public sample key: works without registration, but is shared by
# every project using it and aggressively rate-limited (429) across all of them.
# Public (it ships in their docs), not a secret. If that's all we have, say so
# clearly - both at boot and in the error a farmer would otherwise see.
# See backend/.env.example for how to get your own.
SAMPLE_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"


def _require_key() -> str:
    if not settings.data_gov_api_key:
        raise ExternalDataError(
            "Market data unavailable: set DATA_GOV_API_KEY in backend/.env"
        )
    return settings.data_gov_api_key


def _parse_date(s: str) -> datetime:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return datetime.min


async def _fetch_commodity(client: httpx.AsyncClient, commodity: str, state: str | None, key: str) -> list[dict[str, Any]]:
    params = {
        "api-key": key,
        "format": "json",
        "limit": "60",
        "filters[commodity]": commodity,
    }
    if state:
        params["filters[state]"] = state
    # The upstream blips intermittently; one quick retry rides out a transient timeout.
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            r = await client.get(
                f"https://api.data.gov.in/resource/{settings.agmarknet_resource_id}",
                params=params,
                # data.gov.in silently drops requests carrying httpx's default
                # User-Agent (they all time out), so send an explicit one. Set
                # per-request because the client is shared across services.
                headers={"User-Agent": "KrishiMitra/1.0"},
                timeout=8,
            )
            r.raise_for_status()
            return r.json().get("records", [])
        except httpx.HTTPError as e:
            last_exc = e
            if attempt == 0:
                await asyncio.sleep(0.3)
    assert last_exc is not None
    raise last_exc


async def _crop_item(client: httpx.AsyncClient, crop: str, state: str | None, key: str) -> dict[str, Any] | None:
    """Fetch + summarize one crop, falling back to cache on upstream failure."""
    cache_key = (crop.lower(), state)
    cached = _cache.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    try:
        records = await _fetch_commodity(client, crop, state, key)
        if not records and state:  # widen to all-India if nothing in state
            records = await _fetch_commodity(client, crop, None, key)
        item = _summarize_crop(crop, records)
    except httpx.HTTPError as e:
        if cached:
            logger.warning("market: %s fetch failed (%s); serving stale cache", crop, e)
            return cached[1]
        logger.warning("market: %s fetch failed (%s); no cache", crop, e)
        return None
    if item:
        _cache[cache_key] = (time.time(), item)
    return item


async def get_prices(crops: list[str], state: str | None = None) -> dict[str, Any]:
    key = _require_key()
    # Fetch crops concurrently so total latency ~= the slowest single call, not the
    # sum - critical under the dashboard's tight market budget. Cap crops queried.
    # The shared pooled client keeps connections warm across requests (the UA and
    # timeout are set per-request in _fetch_commodity).
    client = http.get_client()
    results = await asyncio.gather(
        *(_crop_item(client, crop, state, key) for crop in crops[:6])
    )
    out = [item for item in results if item]

    if not out:
        if settings.data_gov_api_key == SAMPLE_KEY:
            raise ExternalDataError(
                "Market data unavailable: the shared data.gov.in sample key is rate-limited. "
                "Set your own free DATA_GOV_API_KEY in backend/.env."
            )
        raise ExternalDataError("No mandi prices found for your crops right now.")
    return {"source": "agmarknet", "items": out}


def _summarize_crop(crop: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = [r for r in records if r.get("modal_price")]
    if not rows:
        return None
    rows.sort(key=lambda r: _parse_date(r.get("arrival_date", "")))

    latest = rows[-1]
    market = latest.get("market") or latest.get("district") or "local mandi"
    current = float(latest["modal_price"])

    # real history (dedup by date, keep last per day)
    history: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        d = r.get("arrival_date", "")
        if d in seen:
            continue
        seen.add(d)
        history.append({"date": _parse_date(d).strftime("%Y-%m-%d"), "price": round(float(r["modal_price"]))})
    history = history[-7:]

    change_pct = 0.0
    if len(history) >= 2 and history[0]["price"]:
        change_pct = round((history[-1]["price"] - history[0]["price"]) / history[0]["price"] * 100, 1)
    trend = "rising" if change_pct > 1.5 else "falling" if change_pct < -1.5 else "stable"

    return {
        "crop": crop,
        "mandi": market,
        "state": latest.get("state"),
        "arrival_date": latest.get("arrival_date"),
        "price_per_quintal": round(current),
        "min_price": round(float(latest.get("min_price", current))),
        "max_price": round(float(latest.get("max_price", current))),
        "change_pct": change_pct,
        "trend": trend,
        "history": history,
        "advice": (
            f"Up {change_pct}% recently - momentum is positive."
            if trend == "rising"
            else f"Down {abs(change_pct)}% recently - sell soon if you must."
            if trend == "falling"
            else "Prices steady - sell at convenience."
        ),
    }
