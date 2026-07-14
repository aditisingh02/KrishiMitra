"""Supported farmer languages - shared across agents and notifications."""

LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "native": "English", "tts": "en-IN", "script": "Latin"},
    "hi": {"name": "Hindi", "native": "हिंदी", "tts": "hi-IN", "script": "Devanagari"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "tts": "pa-IN", "script": "Gurmukhi"},
    "mr": {"name": "Marathi", "native": "मराठी", "tts": "mr-IN", "script": "Devanagari"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "tts": "ta-IN", "script": "Tamil"},
    "te": {"name": "Telugu", "native": "తెలుగు", "tts": "te-IN", "script": "Telugu"},
    "bn": {"name": "Bengali", "native": "বাংলা", "tts": "bn-IN", "script": "Bengali"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "tts": "gu-IN", "script": "Gujarati"},
}

DEFAULT = "hi"


def info(code: str | None) -> dict[str, str]:
    return LANGUAGES.get((code or DEFAULT).lower(), LANGUAGES[DEFAULT])


def name(code: str | None) -> str:
    """Full language name for prompting, e.g. 'Punjabi (in Gurmukhi script)'."""
    i = info(code)
    return f"{i['name']} (in {i['script']} script)"
