"""Market service - real mandi prices from data.gov.in (Agmarknet).

Resource: "Current Daily Price of Various Commodities from Various Markets".
Requires DATA_GOV_API_KEY. Raises ExternalDataError on missing key / failure.

Agmarknet's daily resource is a single-day snapshot (no time series), so we report
only real values: today's modal price at each reporting mandi, the spread across
markets, the best place to sell, and the local rate vs the regional average.

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
        elif state:
            # This dataset is a single-day snapshot, so our "history" is the spread of
            # prices across the mandis reporting today. If the farmer's state has fewer
            # than two markets, there's nothing to compare (and no line to draw), so
            # enrich with all-India rows.
            distinct = {(r.get("market") or r.get("district")) for r in records if r.get("modal_price")}
            if len(distinct) < 2:
                records = records + await _fetch_commodity(client, crop, None, key)
        item = _summarize_crop(crop, records, home_state=state)
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

    # Persist today's snapshot per crop and attach the accumulated day-over-day
    # trend. Best-effort: a history hiccup must never blank the live prices.
    await asyncio.gather(*(_persist_and_attach_history(item, state) for item in out))
    return {"source": "agmarknet", "items": out}


def _snapshot_date(arrival: str | None) -> str:
    d = _parse_date(arrival or "")
    return (d if d != datetime.min else datetime.now()).strftime("%Y-%m-%d")


async def _persist_and_attach_history(item: dict[str, Any], state: str | None) -> None:
    """Store today's price for this crop+region, then attach the stored trend."""
    from app.services import memory  # local import avoids an import cycle at module load

    region = state or item.get("state") or "ALL"
    date = _snapshot_date(item.get("arrival_date"))
    try:
        await memory.memory.record_price_snapshot(
            item["crop"], region, date,
            item["price_per_quintal"], item["min_price"], item["max_price"],
            item.get("markets_count", 1),
        )
        hist = await memory.memory.price_history(item["crop"], region, days=14)
    except Exception as e:
        logger.warning("market: price history failed for %s: %s", item.get("crop"), e)
        hist = []
    item["trend_history"] = hist
    # A real day-over-day change only exists once we have two distinct days stored.
    if len(hist) >= 2 and hist[0]["price"]:
        item["trend_change_pct"] = round(
            (hist[-1]["price"] - hist[0]["price"]) / hist[0]["price"] * 100, 1
        )
        item["trend_days"] = len(hist)


def _summarize_crop(
    crop: str, records: list[dict[str, Any]], home_state: str | None = None
) -> dict[str, Any] | None:
    """Summarize one crop from a single-day, multi-market snapshot.

    Agmarknet's "Current Daily Price" resource has no time series - every record is
    from the same day across different mandis. So instead of a (fake) day-over-day
    trend, we build a real *cross-market* comparison: today's price at each reporting
    mandi, the spread (low -> high), the best place to sell, and how the farmer's
    local rate sits against the regional average.
    """
    rows = [r for r in records if r.get("modal_price")]
    if not rows:
        return None

    # One entry per market (if a market lists several varieties, keep the highest modal).
    by_market: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = (r.get("market") or r.get("district") or "").strip()
        if not name:
            continue
        price = round(float(r["modal_price"]))
        prev = by_market.get(name)
        if prev is None or price > prev["price"]:
            by_market[name] = {"market": name, "price": price, "state": r.get("state")}
    markets = list(by_market.values())
    if not markets:
        return None

    prices = [m["price"] for m in markets]
    avg = sum(prices) / len(prices)
    low, high = min(prices), max(prices)
    best = max(markets, key=lambda m: m["price"])

    # Representative "your area" price: prefer a market in the farmer's state, else the
    # median across every reporting market (robust to one outlier mandi).
    home = [m for m in markets if home_state and (m.get("state") or "").lower() == home_state.lower()]
    pool = sorted(home or markets, key=lambda m: m["price"])
    local = pool[len(pool) // 2]
    current = local["price"]

    # "change" is now the local price vs the regional average today (not over time).
    change_pct = round((current - avg) / avg * 100, 1) if avg else 0.0
    trend = "rising" if change_pct > 1.5 else "falling" if change_pct < -1.5 else "stable"

    # Chart series: every mandi's price today, sorted low -> high so the sparkline
    # reads as the price spread across markets.
    history = [
        {"market": m["market"], "price": m["price"]}
        for m in sorted(markets, key=lambda m: m["price"])
    ]

    if len(markets) >= 2 and best["price"] > current * 1.02:
        gain = round((best["price"] - current) / current * 100)
        advice = f"Best price today: ₹{best['price']}/quintal at {best['market']} - {gain}% above your local rate."
    elif len(markets) >= 2:
        advice = f"Prices even across {len(markets)} mandis today (₹{low}-₹{high}/quintal) - sell at convenience."
    else:
        advice = f"Only one mandi reporting today (₹{current}/quintal) - check back for more markets to compare."

    return {
        "crop": crop,
        "mandi": local["market"],
        "state": local.get("state"),
        "arrival_date": rows[-1].get("arrival_date"),
        "price_per_quintal": current,
        "min_price": low,
        "max_price": high,
        "avg_price": round(avg),
        "change_pct": change_pct,
        "trend": trend,
        "markets_count": len(markets),
        "best_market": best["market"],
        "best_price": best["price"],
        "history": history,
        "advice": advice,
    }
