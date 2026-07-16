"""/api/i18n stays public (the landing page needs it pre-sign-in) but bounded.

It calls the LLM per uncached string, so without caps a loop of unique strings is
an open-ended bill against an unauthenticated endpoint.
"""
from __future__ import annotations

import pytest

from app.api import routes
from app.services import i18n


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Never call Fireworks in tests - echo the input back."""

    async def fake_translate(strings, lang):
        return {s: f"[{lang}] {s}" for s in strings}

    monkeypatch.setattr(i18n, "translate", fake_translate)
    monkeypatch.setattr(routes.i18n, "translate", fake_translate)


def test_i18n_is_public_no_auth_required(client):
    resp = client.post("/api/i18n", json={"lang": "hi", "strings": ["Dashboard"]})
    assert resp.status_code == 200
    assert resp.json()["translations"]["Dashboard"] == "[hi] Dashboard"


def test_too_many_strings_rejected(client):
    resp = client.post(
        "/api/i18n",
        json={"lang": "hi", "strings": [f"s{i}" for i in range(1000)]},
    )
    assert resp.status_code == 413
    assert "Too many strings" in resp.json()["detail"]


def test_batch_at_cap_accepted(client):
    from app.core.config import settings

    resp = client.post(
        "/api/i18n",
        json={"lang": "hi", "strings": [f"s{i}" for i in range(settings.i18n_max_strings)]},
    )
    assert resp.status_code == 200


def test_oversized_string_rejected(client):
    resp = client.post("/api/i18n", json={"lang": "hi", "strings": ["x" * 5000]})
    assert resp.status_code == 413
    assert "characters" in resp.json()["detail"]


def test_normal_batch_accepted(client):
    resp = client.post(
        "/api/i18n", json={"lang": "ta", "strings": ["Dashboard", "Market", "Diagnose"]}
    )
    assert resp.status_code == 200
    assert len(resp.json()["translations"]) == 3
