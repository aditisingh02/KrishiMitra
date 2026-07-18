"""Profile -> many farms, active-farm resolution, and ownership scoping."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.routes import ActiveFarmRequest, FarmCreate, ProfileCreate
from app.core import auth


# ---------- onboarding models ----------
def test_profile_create_requires_name_and_location():
    with pytest.raises(ValidationError):
        ProfileCreate(name="", location="Nashik, Maharashtra")
    with pytest.raises(ValidationError):
        ProfileCreate(name="Aditi", location="")


def test_profile_create_defaults_language_hi():
    assert ProfileCreate(name="Aditi", location="Nashik, Maharashtra").language == "hi"


def test_farm_create_requires_name_and_location():
    with pytest.raises(ValidationError):
        FarmCreate(name="", location="Nashik")
    farm = FarmCreate(name="North plot", location="Nashik, Maharashtra")
    assert farm.name == "North plot"


def test_farm_create_has_no_identity_fields():
    for field in ("farmer", "phone", "language"):
        assert field not in FarmCreate.model_fields


# ---------- get_active_farm dependency ----------
@pytest.mark.asyncio
async def test_active_farm_404_without_profile(monkeypatch):
    from app.services.memory import memory

    async def no_profile(u):
        return None

    monkeypatch.setattr(memory, "get_profile", no_profile)
    with pytest.raises(auth.HTTPException) as e:
        await auth.get_active_farm(user="u1")
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_active_farm_404_when_profile_has_no_farm(monkeypatch):
    from app.services.memory import memory

    async def profile(u):
        return {"id": u, "active_farm_id": None}

    monkeypatch.setattr(memory, "get_profile", profile)
    with pytest.raises(auth.HTTPException) as e:
        await auth.get_active_farm(user="u1")
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_active_farm_resolves_to_id(monkeypatch):
    from app.services.memory import memory

    async def profile(u):
        return {"id": u, "active_farm_id": "farm_abc"}

    async def exists(fid):
        return True

    monkeypatch.setattr(memory, "get_profile", profile)
    monkeypatch.setattr(memory, "farm_exists", exists)
    assert await auth.get_active_farm(user="u1") == "farm_abc"


@pytest.mark.asyncio
async def test_active_farm_404_when_active_id_dangles(monkeypatch):
    """Active farm was deleted out from under the pointer -> 404, not a crash."""
    from app.services.memory import memory

    async def profile(u):
        return {"id": u, "active_farm_id": "gone"}

    async def exists(fid):
        return False

    monkeypatch.setattr(memory, "get_profile", profile)
    monkeypatch.setattr(memory, "farm_exists", exists)
    with pytest.raises(auth.HTTPException) as e:
        await auth.get_active_farm(user="u1")
    assert e.value.status_code == 404


# ---------- routes ----------
@pytest.mark.asyncio
async def test_create_farm_auto_activates_first(monkeypatch):
    from app.api import routes

    activated: dict = {}

    async def profile_exists(u):
        return True

    async def geocode(place):
        return {"lat": 1.0, "lon": 2.0}

    async def create_farm(user, data):
        return {"id": "farm_new", **data}

    async def get_profile(u):
        return {"id": u, "active_farm_id": None}  # no active yet

    async def set_active(u, fid):
        activated["farm"] = fid
        return True

    async def add_event(*a, **k):
        return None

    monkeypatch.setattr(routes.memory, "profile_exists", profile_exists)
    monkeypatch.setattr(routes.weather, "geocode", geocode)
    monkeypatch.setattr(routes.memory, "create_farm", create_farm)
    monkeypatch.setattr(routes.memory, "get_profile", get_profile)
    monkeypatch.setattr(routes.memory, "set_active_farm", set_active)
    monkeypatch.setattr(routes.memory, "add_event", add_event)

    out = await routes.create_farm(
        FarmCreate(name="North plot", location="Nashik, Maharashtra"), user="u1"
    )
    assert out["farm"]["id"] == "farm_new"
    assert activated["farm"] == "farm_new", "first farm must auto-activate"


@pytest.mark.asyncio
async def test_switch_active_farm_checks_ownership(monkeypatch):
    from app.api import routes

    async def set_active(u, fid):
        return False  # not owned

    monkeypatch.setattr(routes.memory, "set_active_farm", set_active)
    with pytest.raises(routes.HTTPException) as e:
        await routes.switch_active_farm(ActiveFarmRequest(farm_id="not_mine"), user="u1")
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_second_farm_does_not_steal_active(monkeypatch):
    """Adding a 2nd farm must not change which farm is active."""
    from app.api import routes

    calls = {"set_active": 0}

    async def profile_exists(u):
        return True

    async def geocode(place):
        return {"lat": 1.0, "lon": 2.0}

    async def create_farm(user, data):
        return {"id": "farm_2", **data}

    async def get_profile(u):
        return {"id": u, "active_farm_id": "farm_1"}  # already has an active farm

    async def set_active(u, fid):
        calls["set_active"] += 1
        return True

    async def add_event(*a, **k):
        return None

    monkeypatch.setattr(routes.memory, "profile_exists", profile_exists)
    monkeypatch.setattr(routes.weather, "geocode", geocode)
    monkeypatch.setattr(routes.memory, "create_farm", create_farm)
    monkeypatch.setattr(routes.memory, "get_profile", get_profile)
    monkeypatch.setattr(routes.memory, "set_active_farm", set_active)
    monkeypatch.setattr(routes.memory, "add_event", add_event)

    await routes.create_farm(FarmCreate(name="South plot", location="Pune, Maharashtra"), user="u1")
    assert calls["set_active"] == 0, "an existing active farm must be left alone"
