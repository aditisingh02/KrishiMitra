"""Agronomic safety guardrail - dosages and substances checked against the KB."""
from __future__ import annotations

import pytest

from app.agents import safety


# ---- prohibited substances ----
@pytest.mark.parametrize("chem", ["monocrotophos", "glyphosate", "chlorpyrifos", "endosulfan"])
def test_prohibited_substance_is_blocking(chem):
    report = safety.check_text(f"Spray {chem} on the affected leaves.")
    assert not report.safe
    assert any(chem in b for b in report.blocking)


def test_synthetic_fertiliser_is_blocking():
    report = safety.check_text("Apply urea to correct the nitrogen deficiency.")
    assert not report.safe


def test_prohibited_match_is_word_bounded():
    """Substring hits must not fire - 'urease' contains 'urea' but isn't it."""
    assert safety.find_prohibited("soil urease enzyme activity is high") == []


def test_natural_remedy_is_safe():
    report = safety.check_text("Spray neem oil in the evening on leaf undersides.")
    assert report.safe


# ---- dosage cross-check ----
def test_kb_matching_dosage_passes():
    """The KB states 5ml neem oil + 1ml soap per litre."""
    report = safety.check_text(
        "Neem oil spray: mix 5ml neem oil and 1ml liquid soap per litre of water."
    )
    assert report.safe, report.blocking


def test_dosage_contradicting_kb_is_blocking():
    """500ml/litre of neem oil is ~100x the KB dose - must not reach a farmer."""
    report = safety.check_text("Neem oil spray: mix 500ml neem oil per litre of water.")
    assert not report.safe
    assert any("contradicts" in b for b in report.blocking)


def test_rescaled_dose_is_allowed():
    """Correct advice rescales constantly. KB says 5ml/litre; 20ml for 4 litres is
    the same concentration and must not be blocked."""
    report = safety.check_text("Neem oil spray: mix 20ml neem oil in 4 litres of water.")
    assert report.safe, report.blocking


def test_ratio_expressed_as_volumes_is_not_blocked():
    """Regression from a real WhatsApp consult.

    The KB gives powdery-mildew milk spray as a ratio (1:9). The model correctly
    answered '100ml milk in 1L water' - the same thing in different units - and the
    old literal check blocked it, so the farmer got no answer at all.
    """
    report = safety.check_text(
        "For Powdery Mildew, spray diluted raw milk - 100ml milk in 1L of water."
    )
    assert report.safe, report.blocking
    assert report.warnings  # flagged as unverifiable, but still delivered


def test_dosage_for_one_prep_is_not_checked_against_another():
    """Regression: quantities must be attributed per sentence.

    Both doses below are exactly what the KB states for their own preparation.
    Pooling them across the whole answer checked neem's 5ml against Jeevamrut's
    numbers and blocked a correct answer.
    """
    report = safety.check_text(
        "Apply Jeevamrut at 200L per acre. Then use Neem oil spray at 5ml per litre."
    )
    assert report.safe, report.blocking


def test_jeevamrut_kb_dosage_passes():
    report = safety.check_text("Apply Jeevamrut at 200L per acre via irrigation.")
    assert report.safe, report.blocking


def test_ungrounded_remedy_dosage_warns():
    """A dosage for something the KB never defines is a warning, not a block."""
    report = safety.check_text("Apply 40ml of superfixmagic tonic per litre.")
    assert report.safe
    assert report.warnings


def test_text_without_dosages_is_safe():
    report = safety.check_text("Improve airflow and remove infected leaves.")
    assert report.safe
    assert not report.warnings


# ---- payload verification ----
def test_verify_advice_passes_safe_payload_through():
    payload = {
        "answer_en": "Spray neem oil (5ml per litre) in the evening.",
        "action_plan": [{"step": 1, "action": "Spray neem oil", "when": "evening"}],
    }
    out, report = safety.verify_advice(payload)
    assert report.safe
    assert out["answer_en"] == payload["answer_en"]
    assert out["_safety"]["safe"] is True


def test_verify_advice_redacts_unsafe_payload():
    payload = {
        "answer_en": "Spray monocrotophos immediately.",
        "answer_local": "मोनोक्रोटोफॉस छिड़कें।",
        "action_plan": [{"step": 1, "action": "Spray monocrotophos", "when": "now"}],
    }
    out, report = safety.verify_advice(payload)
    assert not report.safe
    assert out["_blocked"] is True
    assert "monocrotophos" not in out["answer_en"].lower()
    assert "monocrotophos" not in out["answer_local"].lower()
    assert out["action_plan"] == []
    assert out["answer_en"] == safety.SAFE_FALLBACK


def test_verify_advice_checks_nested_action_plan():
    """Unsafe advice hidden in a nested step must still be caught."""
    payload = {
        "answer_en": "Here is your plan.",
        "action_plan": [{"step": 1, "action": "Apply paraquat to the weeds", "when": "now"}],
    }
    out, report = safety.verify_advice(payload)
    assert not report.safe
    assert out["_blocked"] is True


def test_harvest_ignores_internal_keys():
    """_forecast/_prices carry numbers that would false-positive the dosage check."""
    text = safety._harvest_text({"answer_en": "ok", "_prices": {"modal": "2000 kg"}})
    assert "2000" not in text
    assert "ok" in text


def test_quantity_normalisation():
    q = safety._quantities("Use 5 ml and 200L and 3% and 1:10")
    assert "5ml" in q and "200l" in q and "3%" in q and "1:10" in q
