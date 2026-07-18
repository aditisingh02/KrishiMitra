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


# How far a dosage may deviate from the KB before we call it a contradiction.
# Correct advice rescales constantly ("5ml/litre" -> "50ml for 10 litres"), so a
# tight bound would reject good answers. 5x is loose enough for honest rescaling
# and tight enough to catch the failure that actually harms a farmer: an
# order-of-magnitude overdose.
DOSE_TOLERANCE = 5.0

_SENTENCE_RE = re.compile(r"[.!?\n;]+")


def _quantities_by_unit(text: str) -> dict[str, set[float]]:
    """{unit: {values}} for one chunk of text. Ratios collapse to unit 'ratio'."""
    out: dict[str, set[float]] = {}
    for m in _QTY_RE.finditer(text or ""):
        if m.group(5) and m.group(6):  # a:b
            out.setdefault("ratio", set()).add(int(m.group(5)) / max(int(m.group(6)), 1))
            continue
        if m.group(3):
            out.setdefault("%", set()).add(float(m.group(3)))
            continue
        unit = (m.group(2) or "").lower()
        unit = _UNIT_ALIASES.get(unit, unit)
        out.setdefault(unit, set()).add(float(m.group(1)))
    return out


def _kb_topics_in(text: str) -> list[dict[str, str]]:
    """KB entries whose topic is explicitly named in the text."""
    low = (text or "").lower()
    return [c for c in knowledge.KB if c["topic"].lower() in low]


def find_prohibited(text: str) -> list[str]:
    low = (text or "").lower()
    return sorted({p for p in PROHIBITED if re.search(rf"\b{re.escape(p)}\b", low)})


def check_dosages(text: str) -> tuple[list[str], list[str]]:
    """Cross-check dosages against the KB. Returns (blocking, warnings).

    Two hard-won rules, both from real false positives:

    1. **Attribute per sentence, not per document.** Comparing every quantity in an
       answer against the union of every KB entry named anywhere in it means a
       correct "neem oil 5ml/litre" gets checked against *Jeevamrut's* numbers
       merely because another sentence mentioned Jeevamrut. Advice that covers
       several preparations - i.e. good advice - was the most likely to be blocked.

    2. **Only a same-unit magnitude contradiction blocks.** A quantity simply not
       present in the KB is a warning, never a block. The KB gives powdery-mildew
       milk spray as a ratio (1:9); a model correctly saying "100ml milk in 1L
       water" states the same thing in different units. Demanding a literal match
       rejects correct answers, and a farmer who gets nothing is worse off than one
       who gets a verified answer phrased differently.

    What still blocks is the thing that actually hurts: the same preparation, the
    same unit, an order-of-magnitude apart ("500ml neem per litre" vs the KB's 5ml).
    """
    blocking: list[str] = []
    warnings: list[str] = []

    for sentence in _SENTENCE_RE.split(text or ""):
        topics = _kb_topics_in(sentence)
        if not topics:
            continue
        out_units = _quantities_by_unit(sentence)
        if not out_units:
            continue

        kb_units: dict[str, set[float]] = {}
        for chunk in topics:
            for unit, values in _quantities_by_unit(chunk["text"]).items():
                kb_units.setdefault(unit, set()).update(values)
        if not kb_units:
            continue

        named = ", ".join(c["topic"] for c in topics)
        for unit, values in out_units.items():
            kb_values = kb_units.get(unit)
            if not kb_values:
                # Different unit entirely (ratio vs ml). Can't compare - say so,
                # don't reject.
                warnings.append(
                    f"Dosage for {named} given in units the knowledge base doesn't state "
                    f"({unit}) - could not verify"
                )
                continue
            for value in values:
                if any(_within_tolerance(value, kb) for kb in kb_values):
                    continue
                blocking.append(
                    f"Dosage contradicts knowledge base for {named}: "
                    f"{_fmt(value)}{unit} (KB states {', '.join(_fmt(v) + unit for v in sorted(kb_values))})"
                )
    return blocking, warnings


def _within_tolerance(value: float, reference: float) -> bool:
    if value == reference:
        return True
    if value <= 0 or reference <= 0:
        return False
    ratio = value / reference
    return 1 / DOSE_TOLERANCE <= ratio <= DOSE_TOLERANCE


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


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
