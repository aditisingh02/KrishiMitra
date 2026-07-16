"""Agronomic safety guardrail.

The agents prescribe things a farmer will physically apply to a crop they eat and
sell. A hallucinated chemical or a wrong dosage is the highest-consequence
failure this system has, so agent output is checked before it reaches the farmer.

Three deterministic checks, cheapest first:

1. **Prohibited substances** - this is a *natural farming* product. A synthetic or
   banned//hazardous pesticide must never be recommended, whatever the model says.
   Any hit is blocking.
2. **Ungrounded remedies** - a remedy that is not in the RAG knowledge base was
   not grounded in anything. Flagged for review.
3. **Dosage cross-check** - for preparations the KB *does* define, any dosage in
   the output must match a quantity the KB states for that preparation. A
   contradicting number (e.g. "500ml neem oil per litre" vs the KB's 5ml) is
   blocking.

Limits, stated plainly: this is pattern-based, not semantic. It reliably catches
prohibited substances and numerically contradicted dosages for known preparations.
It will not catch a plausible-sounding but wrong instruction phrased without
numbers. It is a backstop for the RAG grounding in the prompts, not a replacement.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.services import knowledge

logger = logging.getLogger("krishimitra.safety")

# Synthetic / hazardous / banned-in-India inputs. A natural-farming agronomist
# has no business recommending any of these.
PROHIBITED = {
    "monocrotophos", "endosulfan", "paraquat", "phorate", "methyl parathion",
    "carbofuran", "phosphamidon", "dichlorvos", "ddvp", "aldicarb", "captafol",
    "glyphosate", "atrazine", "chlorpyrifos", "imidacloprid", "carbendazim",
    "mancozeb", "paraquat dichloride", "triazophos", "dimethoate", "malathion",
    "cypermethrin", "deltamethrin", "acephate", "profenofos", "quinalphos",
    "urea", "dap", "muriate of potash", "npk complex",  # synthetic fertilisers
}

# Quantity token: "5ml", "200 L", "10 kg", "3%", "1:10".
# Units are matched longest-first, and `%` is a separate branch because a
# trailing \b can never follow a non-word character.
_QTY_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(millilitres|millilitre|litres|liters|litre|liter|grams|gram|ml|kgs|kg|l|g)\b"
    r"|\b(\d+(?:\.\d+)?)\s*(%)"
    r"|\b(\d+)\s*:\s*(\d+)\b",
    re.IGNORECASE,
)

_UNIT_ALIASES = {
    "litre": "l", "liter": "l", "litres": "l", "liters": "l",
    "gram": "g", "grams": "g", "kgs": "kg",
    "millilitre": "ml", "millilitres": "ml",
}


class SafetyReport:
    """Outcome of checking one piece of agent output."""

    def __init__(self) -> None:
        self.blocking: list[str] = []
        self.warnings: list[str] = []

    @property
    def safe(self) -> bool:
        return not self.blocking

    def as_dict(self) -> dict[str, Any]:
        return {
            "safe": self.safe,
            "blocking": self.blocking,
            "warnings": self.warnings,
        }


def _trim(value: str) -> str:
    """5.0 -> 5, so the same dose written two ways compares equal."""
    return value.rstrip("0").rstrip(".") if "." in value else value


def _normalise_qty(match: re.Match[str]) -> str:
    if match.group(5) and match.group(6):  # ratio, e.g. 1:10
        return f"{match.group(5)}:{match.group(6)}"
    if match.group(3):  # percentage
        return f"{_trim(match.group(3))}%"
    unit = (match.group(2) or "").lower()
    return f"{_trim(match.group(1))}{_UNIT_ALIASES.get(unit, unit)}"


def _quantities(text: str) -> set[str]:
    return {_normalise_qty(m) for m in _QTY_RE.finditer(text or "")}


def _kb_topics_in(text: str) -> list[dict[str, str]]:
    """KB entries whose topic is explicitly named in the text."""
    low = (text or "").lower()
    return [c for c in knowledge.KB if c["topic"].lower() in low]


def find_prohibited(text: str) -> list[str]:
    low = (text or "").lower()
    return sorted({p for p in PROHIBITED if re.search(rf"\b{re.escape(p)}\b", low)})


def check_dosages(text: str) -> tuple[list[str], list[str]]:
    """Cross-check dosages for KB-known preparations. Returns (blocking, warnings)."""
    blocking: list[str] = []
    warnings: list[str] = []
    topics = _kb_topics_in(text)
    if not topics:
        return blocking, warnings

    out_qty = _quantities(text)
    if not out_qty:
        return blocking, warnings

    # The union of every quantity the KB states for the named preparations.
    kb_qty: set[str] = set()
    for chunk in topics:
        kb_qty |= _quantities(chunk["text"])

    unknown = out_qty - kb_qty
    if unknown and kb_qty:
        named = ", ".join(c["topic"] for c in topics)
        blocking.append(
            f"Dosage not grounded in knowledge base for {named}: "
            f"{', '.join(sorted(unknown))} (KB states: {', '.join(sorted(kb_qty))})"
        )
    return blocking, warnings


def check_text(text: str) -> SafetyReport:
    """Run every check over a blob of advice text."""
    report = SafetyReport()
    if not text or not text.strip():
        return report

    prohibited = find_prohibited(text)
    if prohibited:
        report.blocking.append(
            f"Prohibited/synthetic input recommended: {', '.join(prohibited)}"
        )

    dose_block, dose_warn = check_dosages(text)
    report.blocking.extend(dose_block)
    report.warnings.extend(dose_warn)

    if not _kb_topics_in(text) and _quantities(text):
        report.warnings.append("Dosage given for a remedy not present in the knowledge base")

    return report


def _harvest_text(payload: Any) -> str:
    """Flatten the advice-bearing strings out of an agent JSON payload."""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key.startswith("_"):  # internal (_forecast, _prices, _raw)
                    continue
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return "\n".join(parts)


SAFE_FALLBACK = (
    "I couldn't verify this recommendation against my agronomy knowledge base, so "
    "I'm not going to give you a dosage I'm unsure about. Please re-ask, or check "
    "with your local Krishi Vigyan Kendra (KVK) before applying anything."
)


def verify_advice(payload: dict[str, Any]) -> tuple[dict[str, Any], SafetyReport]:
    """Check an agent payload; redact it if unsafe.

    Returns the (possibly redacted) payload plus the report. On a blocking issue
    we do NOT pass the model's text through - a wrong dosage reaching a farmer is
    worse than no answer.
    """
    report = check_text(_harvest_text(payload))
    if report.safe:
        if report.warnings:
            logger.info("safety warnings: %s", report.warnings)
        payload["_safety"] = report.as_dict()
        return payload, report

    logger.error("BLOCKED unsafe agronomic advice: %s", report.blocking)
    redacted: dict[str, Any] = {
        "answer_en": SAFE_FALLBACK,
        "answer_local": SAFE_FALLBACK,
        "action_plan": [],
        "_safety": report.as_dict(),
        "_blocked": True,
    }
    return redacted, report
