"""Weather service - real OpenWeather only (no synthetic fallback).

Requires OPENWEATHER_API_KEY. Raises ExternalDataError when the key is missing
or the upstream call fails, so the failure surfaces to the user.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core import http
from app.core.config import settings


class ExternalDataError(RuntimeError):
    """Raised when a required external data source is unavailable."""


def _require_key() -> str:
    if not settings.openweather_api_key:
        raise ExternalDataError(
            "Weather unavailable: set OPENWEATHER_API_KEY in backend/.env"
        )
    return settings.openweather_api_key


def _india_biased(place: str) -> str:
    """Append India country code unless the query already names a country."""
    import re

    if re.search(r",\s*(in|india)\s*$", place, re.IGNORECASE):
        return place
    return f"{place},IN"


async def geocode(place: str) -> dict[str, float]:
    """Resolve a place name to {lat, lon} via OpenWeather geocoding (India-biased)."""
    key = _require_key()
    queries = [_india_biased(place), place]  # prefer India, fall back to raw
    try:
        client = http.get_client()
        for q in queries:
            r = await client.get(
                "https://api.openweathermap.org/geo/1.0/direct",
                params={"q": q, "limit": 1, "appid": key},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            if data:
                return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
    except httpx.HTTPError as e:
        raise ExternalDataError(f"Geocoding failed: {e}") from e
    raise ExternalDataError(f"Could not locate '{place}'. Try 'City, State'.")


async def get_forecast(lat: float, lon: float) -> dict[str, Any]:
    """Real 5-day forecast aggregated to daily values."""
    key = _require_key()
    try:
        r = await http.get_client().get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"lat": lat, "lon": lon, "appid": key, "units": "metric"},
            timeout=25,
        )
        r.raise_for_status()
        raw = r.json()
    except httpx.HTTPError as e:
        raise ExternalDataError(f"Weather fetch failed: {e}") from e

    by_day: dict[str, list[dict[str, Any]]] = {}
    for slot in raw.get("list", []):
        by_day.setdefault(slot["dt_txt"][:10], []).append(slot)

    days: list[dict[str, Any]] = []
    for d, slots in list(by_day.items())[:5]:
        temps = [s["main"]["temp"] for s in slots]
        days.append(
            {
                "date": d,
                "temp_max_c": round(max(temps), 1),
                "temp_min_c": round(min(temps), 1),
                "rain_prob": round(max(s.get("pop", 0) for s in slots) * 100),
                "humidity": round(sum(s["main"]["humidity"] for s in slots) / len(slots)),
                "wind_kmph": round(max(s["wind"]["speed"] for s in slots) * 3.6, 1),
                "condition": slots[0]["weather"][0]["main"],
            }
        )
    if not days:
        raise ExternalDataError("Weather returned no forecast data.")

    return {
        "source": "openweather",
        "location": {"lat": lat, "lon": lon},
        "days": days,
        "summary": _summarize(days),
    }


def _summarize(days: list[dict[str, Any]]) -> str:
    max_rain = max(d["rain_prob"] for d in days)
    max_hum = max(d["humidity"] for d in days)
    bits = []
    if max_rain >= 70:
        bits.append(f"high rain probability ({max_rain}%) in the next few days")
    if max_hum >= 78:
        bits.append(f"humidity spiking to {max_hum}%")
    return "; ".join(bits) or "stable, dry conditions"
