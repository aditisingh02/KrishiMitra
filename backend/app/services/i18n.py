"""Runtime UI translation service.

The frontend ships English source strings; this service translates them into the
farmer's language on demand using the LLM (which is strong at Indian languages),
and caches every translation to disk so each string is only ever translated once
per language. English is a pass-through. Cache: data/i18n_cache/<lang>.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.core import languages
from app.core.config import settings
from app.core.fireworks import fireworks

logger = logging.getLogger("krishimitra.i18n")

_CACHE_DIR = Path(settings.db_path).parent / "i18n_cache"
_cache: dict[str, dict[str, str]] = {}
_locks: dict[str, asyncio.Lock] = {}

_SYSTEM = (
    "You are a professional UI localizer for an Indian agriculture app used by farmers. "
    "Translate each English UI string into the target language using natural, simple, "
    "farmer-friendly wording in the target's native script. Keep it concise (UI labels). "
    "Transliterate Indian farming terms, preparation names and crop names into the target's "
    "native script so farmers can read them (e.g. Jeevamrut, Beejamrut, Panchagavya, Cowpea, "
    "Moringa, Vermicompost should appear in the native script, never left in Latin letters). "
    "Preserve placeholders wrapped in braces like {n} exactly. Keep ONLY the app name "
    "'KrishiMitra', units (kg, °C, %) and English technical/model names as-is. "
    'Return ONLY a JSON object mapping each original English string to its translation: '
    '{"English": "translation"}.'
)


def _load(lang: str) -> dict[str, str]:
    if lang in _cache:
        return _cache[lang]
    path = _CACHE_DIR / f"{lang}.json"
    data: dict[str, str] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text("utf-8"))
        except (ValueError, OSError):
            data = {}
    _cache[lang] = data
    return data


def _save(lang: str, data: dict[str, str]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (_CACHE_DIR / f"{lang}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=0), "utf-8"
    )


def _lock(lang: str) -> asyncio.Lock:
    if lang not in _locks:
        _locks[lang] = asyncio.Lock()
    return _locks[lang]


async def translate(strings: list[str], lang: str) -> dict[str, str]:
    """Return {english: translated} for every requested string in `lang`."""
    code = (lang or "en").lower()
    # de-dupe, drop empties
    wanted = [s for s in dict.fromkeys(strings) if s and s.strip()]
    if code == "en" or code not in languages.LANGUAGES:
        return {s: s for s in wanted}

    cached = _load(code)
    missing = [s for s in wanted if s not in cached]

    if missing:
        async with _lock(code):
            cached = _load(code)  # re-read inside lock
            missing = [s for s in wanted if s not in cached]
            if missing:
                fresh = await _translate_via_llm(missing, code)
                cached.update(fresh)
                _cache[code] = cached
                _save(code, cached)

    # fall back to English for anything the model dropped
    return {s: cached.get(s, s) for s in wanted}


async def _translate_via_llm(strings: list[str], code: str) -> dict[str, str]:
    target = languages.name(code)
    # batch in chunks to keep each call small and reliable
    out: dict[str, str] = {}
    CHUNK = 40
    for i in range(0, len(strings), CHUNK):
        chunk = strings[i : i + CHUNK]
        user = f"TARGET LANGUAGE: {target}\n\nTranslate these UI strings:\n{json.dumps(chunk, ensure_ascii=False)}"
        try:
            res = await fireworks.chat_json(
                _SYSTEM, user, model=settings.model_fast, max_tokens=2400
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("i18n translate failed (%s): %s", code, e)
            res = {}
        for s in chunk:
            v = res.get(s) if isinstance(res, dict) else None
            out[s] = v if isinstance(v, str) and v.strip() else s
    return out
