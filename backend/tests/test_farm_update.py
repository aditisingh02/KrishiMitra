"""Farm + profile update validation under the multi-farm model.

Farm updates are farm-level (name/location/crops/soil). Farmer identity
(name/phone/language) is profile-level - the phone-hijack guard lives there.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.routes import FarmUpdate, ProfileUpdate


# ---------- farm-level update ----------
def test_partial_update_only_carries_what_was_sent():
    patch = FarmUpdate(name="North plot").model_dump(exclude_unset=True)
    assert patch == {"name": "North plot"}


def test_farm_update_has_no_identity_fields():
    """Identity is profile-level - it must not be mass-assignable via a farm patch."""
    for field in ("farmer", "phone", "language"):
        assert field not in FarmUpdate.model_fields


@pytest.mark.parametrize("size", [0, -1, 200_000])
def test_absurd_farm_size_rejected(size):
    with pytest.raises(ValidationError):
        FarmUpdate(farm_size_acres=size)


def test_too_many_crops_rejected():
    with pytest.raises(ValidationError):
        FarmUpdate(crops=[{"name": f"crop{i}"} for i in range(100)])


def test_blank_inputs_are_stripped():
    assert FarmUpdate(inputs_on_hand=["  Neem oil  ", "", "   "]).inputs_on_hand == ["Neem oil"]


def test_soil_is_bounded():
    with pytest.raises(ValidationError):
        FarmUpdate(soil={f"k{i}": i for i in range(50)})


def test_extra_fields_ignored():
    patch = FarmUpdate(**{"name": "X", "id": "other", "profile_id": "someone"}).model_dump(
        exclude_unset=True
    )
    assert patch == {"name": "X"}


# ---------- profile-level update (identity + phone) ----------
def test_unknown_language_rejected():
    with pytest.raises(ValidationError):
        ProfileUpdate(language="klingon")


def test_known_language_accepted():
    assert ProfileUpdate(language="ta").language == "ta"


def test_overlong_name_rejected():
    with pytest.raises(ValidationError):
        ProfileUpdate(name="x" * 200)


# ---------- route behaviour ----------
def test_farm_patch_requires_auth(client):
    assert client.patch("/api/farms/abc123", json={"name": "X"}).status_code == 401


def test_profile_patch_requires_auth(client):
    assert client.patch("/api/profile", json={"name": "X"}).status_code == 401


@pytest.mark.asyncio
async def test_phone_hijack_rejected_at_profile_level(monkeypatch):
    """The number-hijack guard now lives on the profile (WhatsApp is profile-level).

    Inbound WhatsApp is routed by number, so if another profile could claim yours,
    your messages would resolve to their account.
    """
    from app.api import routes

    async def exists(user):
        return True

    async def profile_by_phone(phone):
        return {"id": "victim", "name": "Victim"}

    monkeypatch.setattr(routes.memory, "profile_exists", exists)
    monkeypatch.setattr(routes.memory, "profile_by_phone", profile_by_phone)

    with pytest.raises(routes.HTTPException) as e:
        await routes.update_profile(ProfileUpdate(phone="+919324341202"), user="attacker")
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_keeping_your_own_number_is_allowed(monkeypatch):
    from app.api import routes

    saved: dict = {}

    async def exists(user):
        return True

    async def profile_by_phone(phone):
        return {"id": "me"}  # already mine

    async def save_profile(user, patch):
        saved.update(patch)
        return {"id": user, **patch}

    async def list_farms(user):
        return []

    monkeypatch.setattr(routes.memory, "profile_exists", exists)
    monkeypatch.setattr(routes.memory, "profile_by_phone", profile_by_phone)
    monkeypatch.setattr(routes.memory, "save_profile", save_profile)
    monkeypatch.setattr(routes.memory, "list_farms", list_farms)

    await routes.update_profile(ProfileUpdate(phone="+919324341202"), user="me")
    assert saved["phone"] == "+919324341202"


@pytest.mark.asyncio
async def test_empty_phone_unlinks(monkeypatch):
    from app.api import routes

    saved: dict = {}

    async def exists(user):
        return True

    async def save_profile(user, patch):
        saved.update(patch)
        return {"id": user}

    async def list_farms(user):
        return []

    monkeypatch.setattr(routes.memory, "profile_exists", exists)
    monkeypatch.setattr(routes.memory, "save_profile", save_profile)
    monkeypatch.setattr(routes.memory, "list_farms", list_farms)

    await routes.update_profile(ProfileUpdate(phone=""), user="me")
    assert saved["phone"] is None


@pytest.mark.asyncio
async def test_farm_location_change_refreshes_coordinates(monkeypatch):
    """Stale coords would keep forecasting the old village."""
    from app.api import routes

    saved: dict = {}

    async def owns(user, farm_id):
        return True

    async def geocode(place):
        return {"lat": 19.07, "lon": 72.87}

    async def update(patch, farm_id):
        saved.update(patch)
        return {"id": farm_id}

    async def add_event(*a, **k):
        return None

    monkeypatch.setattr(routes.memory, "owns_farm", owns)
    monkeypatch.setattr(routes.weather, "geocode", geocode)
    monkeypatch.setattr(routes.memory, "update_farm", update)
    monkeypatch.setattr(routes.memory, "add_event", add_event)
    monkeypatch.setattr(routes.flows, "invalidate_dashboard", lambda f: None)

    await routes.update_farm("farm123", FarmUpdate(location="Mumbai, Maharashtra"), user="me")
    assert saved["lat"] == 19.07 and saved["lon"] == 72.87


@pytest.mark.asyncio
async def test_update_farm_you_dont_own_is_404(monkeypatch):
    from app.api import routes

    async def owns(user, farm_id):
        return False

    monkeypatch.setattr(routes.memory, "owns_farm", owns)
    with pytest.raises(routes.HTTPException) as e:
        await routes.update_farm("someone_elses", FarmUpdate(name="X"), user="me")
    assert e.value.status_code == 404
