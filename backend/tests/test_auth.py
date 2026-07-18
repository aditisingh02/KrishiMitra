"""Authentication: no route may serve farm data without a valid Clerk JWT."""
from __future__ import annotations

import jwt
import pytest
from fastapi import HTTPException

from app.core import auth

PROTECTED = [
    ("get", "/api/farm"),
    ("get", "/api/profile"),
    ("get", "/api/profile/exists"),
    ("get", "/api/farms"),
    ("get", "/api/dashboard"),
    ("post", "/api/consult"),
    ("post", "/api/weekly-plan"),
    ("get", "/api/notifications"),
    ("post", "/api/monitor/run"),
]


def _call(client, method: str, path: str, **kw):
    # httpx's get() takes no json kwarg - only send a body on POST.
    if method == "post":
        kw.setdefault("json", {})
    return getattr(client, method)(path, **kw)


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_routes_reject_missing_token(client, method, path):
    resp = _call(client, method, path)
    assert resp.status_code == 401, f"{path} served without a token"


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_routes_reject_garbage_token(client, method, path):
    resp = _call(client, method, path, headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_public_routes_need_no_token(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/languages").status_code == 200


@pytest.mark.asyncio
async def test_unsigned_token_is_rejected(monkeypatch):
    """A token signed with `alg: none` must never be accepted."""
    forged = jwt.encode({"sub": "user_evil"}, key="", algorithm="none")

    class Creds:
        credentials = forged

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(_FakeRequest(), Creds())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_issuer_returns_503(monkeypatch):
    monkeypatch.setattr(auth.settings, "clerk_issuer", "")

    class Creds:
        credentials = "whatever"

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(_FakeRequest(), Creds())
    assert exc.value.status_code == 503


class _FakeRequest:
    """Minimal stand-in - get_current_user only writes to request.state."""

    class _State:
        pass

    def __init__(self) -> None:
        self.state = self._State()
