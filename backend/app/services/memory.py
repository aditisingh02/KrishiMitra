"""Farm Memory Agent - the digital twin store.

Acts as a CRM for the farm: crops, soil, disease history, treatments, a running
activity log, notifications, and a semantic long-term memory of past consults and
diagnoses. Backed by PostgreSQL (Render) via async SQLAlchemy, with pgvector for
similarity recall. Profiles live in a JSONB `data` blob (fully customizable);
hot lookup fields (phone/language/coords) are mirrored into indexed columns.

The public surface mirrors the previous SQLite store so callers only needed to
add `await`; two new methods - `add_memory` and `recall` - power semantic recall.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, Integer, String, Text, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.db import Base, SessionLocal
from app.core.fireworks import fireworks


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _profile_dict(p: "Profile") -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "phone": p.phone,
        "language": p.language,
        "default_location": p.default_location,
        "active_farm_id": p.active_farm_id,
    }


def _interaction_dict(r: "Interaction") -> dict[str, Any]:
    return {
        "id": r.id,
        "kind": r.kind,
        "query": r.query,
        "answer": r.answer,
        "answer_en": r.answer_en,
        "payload": r.payload or {},
        "blocked": bool(r.blocked),
        "created_at": r.created_at,
    }


def _task_dict(t: "CalendarTask") -> dict[str, Any]:
    return {
        "id": t.id,
        "cycle_id": t.cycle_id,
        "title": t.title,
        "detail": t.detail,
        "kind": t.kind,
        "due_on": t.due_on,
        "done": bool(t.done),
        "notified_on": t.notified_on,
        "source": t.source,
    }


def _norm_phone(phone: str | None) -> str | None:
    """Last 10 digits, tolerant of +91 / `whatsapp:` prefixes. Used for lookup."""
    if not phone:
        return None
    digits = "".join(ch for ch in str(phone) if ch.isdigit())[-10:]
    return digits or None


# --------------------------------------------------------------------------- #
# ORM models
# --------------------------------------------------------------------------- #
class Profile(Base):
    """The farmer. One per Clerk user. Owns one or more farms.

    Identity + contact live here (name, WhatsApp, language); everything the AI is
    grounded on (crops, soil, location, weather) lives on the individual Farm. The
    AI always operates on ONE farm - `active_farm_id` - so a farmer with plots in
    two villages gets advice for whichever they're currently looking at.
    """

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Clerk user id
    name: Mapped[str] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String, index=True)  # normalized 10-digit
    language: Mapped[str | None] = mapped_column(String)
    default_location: Mapped[str | None] = mapped_column(String)  # seeds new farms
    active_farm_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=_now)
    updated_at: Mapped[str] = mapped_column(String, default=_now)


class Farm(Base):
    __tablename__ = "farms"

    # A generated id, NOT the Clerk user id (a user can own several farms). The
    # farm that predates multi-farm keeps its old id == user id, so the events /
    # notifications / memories / calendar rows already keyed to it stay valid.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    profile_id: Mapped[str] = mapped_column(String, index=True)  # owning Clerk user
    name: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String, index=True)  # denormalized from profile
    language: Mapped[str | None] = mapped_column(String)
    lat: Mapped[float | None] = mapped_column()
    lon: Mapped[float | None] = mapped_column()
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # full farm blob
    created_at: Mapped[str] = mapped_column(String, default=_now)
    updated_at: Mapped[str] = mapped_column(String, default=_now)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String, index=True)
    level: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String, default=_now)


class CropCycle(Base):
    """One planting of one crop: sowing -> harvest.

    The farm profile's `crops` list says *what* is growing; a cycle says *when* it
    went in, which is what every agronomic recommendation is actually keyed on
    (spray at 25 days, top-dress at 40, harvest at 110).
    """

    __tablename__ = "crop_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String, index=True)
    crop: Mapped[str] = mapped_column(String)
    sown_on: Mapped[str] = mapped_column(String)  # ISO date, YYYY-MM-DD
    expected_harvest_on: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")  # active|harvested|abandoned
    created_at: Mapped[str] = mapped_column(String, default=_now)


class CalendarTask(Base):
    """A dated agronomic task on a crop cycle ("Spray neem", "Top-dress").

    `due_on` is computed in Python from the model's day-offset, never taken from
    the model directly - see flows.generate_calendar.

    `notified_on` is the reminder de-dupe: a date once a WhatsApp reminder has
    gone out, NULL before. Without it, a daily monitor would re-remind every
    single day until the task is done.
    """

    __tablename__ = "calendar_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String, index=True)
    # NULL for tasks not tied to a crop cycle (e.g. added from a consult answer).
    cycle_id: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String)  # spray|irrigation|nutrition|scouting|harvest|sowing|other
    # NULL when the timing couldn't be dated (e.g. "next planting season").
    due_on: Mapped[str | None] = mapped_column(String, index=True)  # ISO date
    done: Mapped[int] = mapped_column(Integer, default=0)
    notified_on: Mapped[str | None] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String)  # calendar | consult
    created_at: Mapped[str] = mapped_column(String, default=_now)


class Interaction(Base):
    """Full chat history: one row per consult / diagnose, per farm.

    Distinct from `events` (short activity summaries that feed prompts + the
    dashboard) and `memories` (pgvector semantic recall that embeds every row and
    excludes blocked answers). This is the displayable, paginated conversation
    history - no embedding cost, and it keeps blocked answers so the UI can show
    the same safety banner.
    """

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # consult | diagnose
    query: Mapped[str] = mapped_column(Text)  # question / photo note
    answer: Mapped[str | None] = mapped_column(Text)  # local answer, for display
    answer_en: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    blocked: Mapped[int] = mapped_column(Integer, default=0)  # safety guardrail withheld it
    created_at: Mapped[str] = mapped_column(String, default=_now)

    __table_args__ = (Index("ix_interactions_farm_kind", "farm_id", "kind"),)


class Memory(Base):
    """Semantic long-term memory: embedded past consults / diagnoses per farm."""

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embed_dim))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=_now)

    __table_args__ = (
        Index(
            "ix_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class FarmMemory:
    # ---------- profile (the farmer; keyed by Clerk user id) ----------
    async def get_profile(self, user_id: str) -> dict[str, Any] | None:
        async with SessionLocal() as s:
            row = await s.get(Profile, user_id)
            return _profile_dict(row) if row else None

    async def profile_exists(self, user_id: str) -> bool:
        async with SessionLocal() as s:
            return await s.get(Profile, user_id) is not None

    async def save_profile(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        async with SessionLocal() as s:
            row = await s.get(Profile, user_id)
            if row is None:
                row = Profile(id=user_id, name=patch.get("name") or "Farmer", created_at=now)
                s.add(row)
            for field in ("name", "language", "active_farm_id"):
                if field in patch and patch[field] is not None:
                    setattr(row, field, patch[field])
            if "default_location" in patch:
                row.default_location = patch["default_location"]
            if "phone" in patch:
                row.phone = _norm_phone(patch["phone"])  # None clears the link
            row.updated_at = now
            await s.commit()
            saved = _profile_dict(row)
        # Identity is denormalized onto each farm so the agent layer never has to
        # join - keep the copies in step when the profile changes.
        if any(k in patch for k in ("name", "language", "phone")):
            await self._propagate_to_farms(user_id, saved)
        return saved

    async def profile_by_phone(self, phone: str) -> dict[str, Any] | None:
        """Resolve an inbound WhatsApp number to a profile (indexed, normalized)."""
        digits = _norm_phone(phone)
        if not digits:
            return None
        async with SessionLocal() as s:
            row = (
                await s.execute(select(Profile).where(Profile.phone == digits))
            ).scalars().first()
            return _profile_dict(row) if row else None

    async def set_active_farm(self, user_id: str, farm_id: str) -> bool:
        async with SessionLocal() as s:
            profile = await s.get(Profile, user_id)
            farm = await s.get(Farm, farm_id)
            if not profile or not farm or farm.profile_id != user_id:
                return False  # can't activate a farm you don't own
            profile.active_farm_id = farm_id
            profile.updated_at = _now()
            await s.commit()
            return True

    async def _propagate_to_farms(self, user_id: str, profile: dict[str, Any]) -> None:
        async with SessionLocal() as s:
            rows = (
                await s.execute(select(Farm).where(Farm.profile_id == user_id))
            ).scalars().all()
            for row in rows:
                data = dict(row.data)
                data["farmer"] = profile.get("name")
                data["language"] = profile.get("language")
                data["phone"] = profile.get("phone")
                row.data = data
                row.language = profile.get("language")
                row.phone = _norm_phone(profile.get("phone"))
            await s.commit()

    # ---------- farms (one profile -> many) ----------
    async def get_farm(self, farm_id: str) -> dict[str, Any]:
        async with SessionLocal() as s:
            row = await s.get(Farm, farm_id)
            return dict(row.data) if row else {}

    async def farm_exists(self, farm_id: str) -> bool:
        async with SessionLocal() as s:
            return await s.get(Farm, farm_id) is not None

    async def owns_farm(self, user_id: str, farm_id: str) -> bool:
        async with SessionLocal() as s:
            row = await s.get(Farm, farm_id)
            return bool(row and row.profile_id == user_id)

    async def list_farms(self, user_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as s:
            rows = (
                await s.execute(
                    select(Farm).where(Farm.profile_id == user_id).order_by(Farm.created_at)
                )
            ).scalars().all()
            return [dict(r.data) for r in rows]

    async def all_farms(self) -> list[dict[str, Any]]:
        async with SessionLocal() as s:
            rows = (await s.execute(select(Farm.data))).scalars().all()
        return [dict(d) for d in rows]

    async def create_farm(self, user_id: str, farm: dict[str, Any]) -> dict[str, Any]:
        """Create a new farm under a profile, stamping the owner's identity onto it."""
        farm_id = uuid.uuid4().hex
        profile = await self.get_profile(user_id) or {}
        farm = {
            **farm,
            "id": farm_id,
            "profile_id": user_id,
            "farmer": profile.get("name"),
            "language": profile.get("language"),
            "phone": profile.get("phone"),
        }
        return await self._write_farm(farm, farm_id, user_id)

    async def save_farm(self, farm: dict[str, Any], farm_id: str) -> dict[str, Any]:
        """Update an existing farm in place (keeps id + owner)."""
        async with SessionLocal() as s:
            row = await s.get(Farm, farm_id)
            owner = row.profile_id if row else farm.get("profile_id")
        return await self._write_farm({**farm, "id": farm_id}, farm_id, owner)

    async def _write_farm(self, farm: dict[str, Any], farm_id: str, owner: str | None) -> dict[str, Any]:
        now = _now()
        farm = {**farm, "id": farm_id, "profile_id": owner}
        async with SessionLocal() as s:
            row = await s.get(Farm, farm_id)
            if row is None:
                row = Farm(id=farm_id, profile_id=owner, created_at=now)
                s.add(row)
            row.profile_id = owner
            row.name = farm.get("name")
            row.data = farm
            row.phone = _norm_phone(farm.get("phone"))
            row.language = farm.get("language")
            row.lat = farm.get("lat")
            row.lon = farm.get("lon")
            row.updated_at = now
            await s.commit()
        return farm

    async def update_farm(self, patch: dict[str, Any], farm_id: str) -> dict[str, Any]:
        farm = await self.get_farm(farm_id)
        farm.update(patch)
        return await self.save_farm(farm, farm_id)

    async def delete_farm(self, user_id: str, farm_id: str) -> bool:
        async with SessionLocal() as s:
            row = await s.get(Farm, farm_id)
            if not row or row.profile_id != user_id:
                return False
            # Remove the farm's dependent rows so nothing dangles.
            for model in (Event, Notification, CropCycle, CalendarTask, Memory, Interaction):
                await s.execute(delete(model).where(model.farm_id == farm_id))
            await s.delete(row)
            # If this was the active farm, fall back to another of the profile's farms.
            profile = await s.get(Profile, user_id)
            if profile and profile.active_farm_id == farm_id:
                other = (
                    await s.execute(
                        select(Farm.id).where(Farm.profile_id == user_id, Farm.id != farm_id).limit(1)
                    )
                ).scalars().first()
                profile.active_farm_id = other
            await s.commit()
            return True

    # ---------- events / history ----------
    async def add_event(
        self,
        kind: str,
        summary: str,
        detail: dict[str, Any] | None,
        farm_id: str,
    ) -> None:
        async with SessionLocal() as s:
            s.add(
                Event(
                    farm_id=farm_id,
                    kind=kind,
                    summary=summary,
                    detail=detail or {},
                    created_at=_now(),
                )
            )
            await s.commit()

    async def recent_events(self, limit: int, farm_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as s:
            rows = (
                await s.execute(
                    select(Event)
                    .where(Event.farm_id == farm_id)
                    .order_by(Event.id.desc())
                    .limit(limit)
                )
            ).scalars().all()
        return [
            {
                "kind": r.kind,
                "summary": r.summary,
                "detail": r.detail or {},
                "created_at": r.created_at,
            }
            for r in rows
        ]

    async def record_disease(self, disease: str, crop: str, farm_id: str) -> None:
        farm = await self.get_farm(farm_id)
        history = farm.get("recent_diseases", [])
        entry = {"disease": disease, "crop": crop, "date": _now()[:10]}
        history = [entry] + [h for h in history if h.get("disease") != disease][:9]
        await self.update_farm({"recent_diseases": history}, farm_id)
        await self.add_event("diagnosis", f"{disease} detected on {crop}", entry, farm_id)

    # ---------- notifications ----------
    async def add_notification(self, farm_id: str, level: str, title: str, body: str) -> int:
        async with SessionLocal() as s:
            note = Notification(
                farm_id=farm_id, level=level, title=title, body=body, read=0, created_at=_now()
            )
            s.add(note)
            await s.commit()
            return note.id

    async def list_notifications(self, farm_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with SessionLocal() as s:
            rows = (
                await s.execute(
                    select(Notification)
                    .where(Notification.farm_id == farm_id)
                    .order_by(Notification.id.desc())
                    .limit(limit)
                )
            ).scalars().all()
        return [
            {
                "id": r.id,
                "level": r.level,
                "title": r.title,
                "body": r.body,
                "read": r.read,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    async def unread_count(self, farm_id: str) -> int:
        async with SessionLocal() as s:
            return (
                await s.execute(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.farm_id == farm_id, Notification.read == 0)
                )
            ).scalar_one()

    async def mark_notifications_read(self, farm_id: str) -> None:
        async with SessionLocal() as s:
            rows = (
                await s.execute(
                    select(Notification).where(
                        Notification.farm_id == farm_id, Notification.read == 0
                    )
                )
            ).scalars().all()
            for r in rows:
                r.read = 1
            await s.commit()

    async def notification_exists_today(self, farm_id: str, title: str) -> bool:
        today = _now()[:10]
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(Notification.id).where(
                        Notification.farm_id == farm_id,
                        Notification.title == title,
                        Notification.created_at.like(f"{today}%"),
                    )
                )
            ).first()
        return row is not None

    # ---------- semantic long-term memory (pgvector) ----------
    async def add_memory(
        self,
        farm_id: str,
        kind: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Embed `text` and store it as recallable long-term memory for the farm."""
        text = (text or "").strip()
        if not text:
            return
        embedding = await fireworks.embed(text)
        async with SessionLocal() as s:
            s.add(
                Memory(
                    farm_id=farm_id,
                    kind=kind,
                    text=text,
                    embedding=embedding,
                    meta=meta or {},
                    created_at=_now(),
                )
            )
            await s.commit()

    async def recall(self, farm_id: str, query: str, k: int = 4) -> list[dict[str, Any]]:
        """Return the k most semantically relevant past memories for this farm."""
        query = (query or "").strip()
        if not query:
            return []
        embedding = await fireworks.embed(query)
        async with SessionLocal() as s:
            rows = (
                await s.execute(
                    select(Memory)
                    .where(Memory.farm_id == farm_id)
                    .order_by(Memory.embedding.cosine_distance(embedding))
                    .limit(k)
                )
            ).scalars().all()
        return [
            {"kind": r.kind, "text": r.text, "meta": r.meta or {}, "created_at": r.created_at}
            for r in rows
        ]

    # ---------- interactions (chat history: consult / diagnose) ----------
    async def add_interaction(
        self,
        farm_id: str,
        kind: str,
        query: str,
        answer: str | None,
        answer_en: str | None,
        payload: dict[str, Any] | None = None,
        blocked: bool = False,
    ) -> int:
        async with SessionLocal() as s:
            row = Interaction(
                farm_id=farm_id,
                kind=kind,
                query=(query or "")[:2000],
                answer=answer,
                answer_en=answer_en,
                payload=payload or {},
                blocked=1 if blocked else 0,
                created_at=_now(),
            )
            s.add(row)
            await s.commit()
            return row.id

    async def list_interactions(
        self, farm_id: str, kind: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """History newest-first. Ordered by id (monotonic, index-backed)."""
        async with SessionLocal() as s:
            q = select(Interaction).where(Interaction.farm_id == farm_id)
            if kind is not None:
                q = q.where(Interaction.kind == kind)
            rows = (
                await s.execute(q.order_by(Interaction.id.desc()).limit(max(1, min(limit, 100))))
            ).scalars().all()
            return [_interaction_dict(r) for r in rows]

    async def recent_interactions(self, farm_id: str, limit: int = 5) -> list[dict[str, Any]]:
        return await self.list_interactions(farm_id, limit=limit)

    async def get_interaction(self, farm_id: str, interaction_id: int) -> dict[str, Any] | None:
        """Farm-scoped fetch of one interaction (for 'add to planner' re-read)."""
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(Interaction).where(
                        Interaction.id == interaction_id, Interaction.farm_id == farm_id
                    )
                )
            ).scalars().first()
            return _interaction_dict(row) if row else None

    # ---------- compact context for prompts ----------
    # ---------- crop calendar ----------
    async def add_cycle(
        self, farm_id: str, crop: str, sown_on: str, expected_harvest_on: str | None
    ) -> int:
        async with SessionLocal() as s:
            cycle = CropCycle(
                farm_id=farm_id,
                crop=crop,
                sown_on=sown_on,
                expected_harvest_on=expected_harvest_on,
                status="active",
            )
            s.add(cycle)
            await s.commit()
            return cycle.id

    async def list_cycles(self, farm_id: str, *, active_only: bool = False) -> list[dict[str, Any]]:
        async with SessionLocal() as s:
            q = select(CropCycle).where(CropCycle.farm_id == farm_id)
            if active_only:
                q = q.where(CropCycle.status == "active")
            rows = (await s.execute(q.order_by(CropCycle.sown_on.desc()))).scalars().all()
            return [
                {
                    "id": c.id,
                    "crop": c.crop,
                    "sown_on": c.sown_on,
                    "expected_harvest_on": c.expected_harvest_on,
                    "status": c.status,
                }
                for c in rows
            ]

    async def get_cycle(self, farm_id: str, cycle_id: int) -> dict[str, Any] | None:
        """Scoped by farm_id on purpose - never look a cycle up by id alone."""
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(CropCycle).where(
                        CropCycle.id == cycle_id, CropCycle.farm_id == farm_id
                    )
                )
            ).scalars().first()
            if not row:
                return None
            return {
                "id": row.id,
                "crop": row.crop,
                "sown_on": row.sown_on,
                "expected_harvest_on": row.expected_harvest_on,
                "status": row.status,
            }

    async def set_cycle_status(self, farm_id: str, cycle_id: int, status: str) -> bool:
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(CropCycle).where(
                        CropCycle.id == cycle_id, CropCycle.farm_id == farm_id
                    )
                )
            ).scalars().first()
            if not row:
                return False
            row.status = status
            await s.commit()
            return True

    async def delete_cycle(self, farm_id: str, cycle_id: int) -> bool:
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(CropCycle).where(
                        CropCycle.id == cycle_id, CropCycle.farm_id == farm_id
                    )
                )
            ).scalars().first()
            if not row:
                return False
            await s.execute(
                delete(CalendarTask).where(
                    CalendarTask.cycle_id == cycle_id, CalendarTask.farm_id == farm_id
                )
            )
            await s.delete(row)
            await s.commit()
            return True

    async def add_tasks(
        self, farm_id: str, cycle_id: int | None = None, tasks: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Bulk-insert tasks. `cycle_id=None` for cycle-less (e.g. consult) tasks;
        `due_on` may be None (undated). Returns the inserted rows."""
        tasks = tasks or []
        if not tasks:
            return []
        async with SessionLocal() as s:
            rows = [
                CalendarTask(
                    farm_id=farm_id,
                    cycle_id=cycle_id,
                    title=t["title"],
                    detail=t.get("detail"),
                    kind=t.get("kind", "other"),
                    due_on=t.get("due_on"),
                    source=t.get("source"),
                )
                for t in tasks
            ]
            s.add_all(rows)
            await s.commit()
            return [_task_dict(r) for r in rows]

    async def list_tasks(
        self,
        farm_id: str,
        *,
        cycle_id: int | None = None,
        include_done: bool = True,
    ) -> list[dict[str, Any]]:
        async with SessionLocal() as s:
            q = select(CalendarTask).where(CalendarTask.farm_id == farm_id)
            if cycle_id is not None:
                q = q.where(CalendarTask.cycle_id == cycle_id)
            if not include_done:
                q = q.where(CalendarTask.done == 0)
            rows = (await s.execute(q.order_by(CalendarTask.due_on))).scalars().all()
            return [_task_dict(t) for t in rows]

    async def due_tasks(self, farm_id: str, on_or_before: str) -> list[dict[str, Any]]:
        """Undone, un-notified tasks due on/before a date - the reminder queue."""
        async with SessionLocal() as s:
            rows = (
                await s.execute(
                    select(CalendarTask)
                    .where(
                        CalendarTask.farm_id == farm_id,
                        CalendarTask.done == 0,
                        CalendarTask.notified_on.is_(None),
                        CalendarTask.due_on <= on_or_before,
                    )
                    .order_by(CalendarTask.due_on)
                )
            ).scalars().all()
            return [_task_dict(t) for t in rows]

    async def set_task_done(self, farm_id: str, task_id: int, done: bool) -> bool:
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(CalendarTask).where(
                        CalendarTask.id == task_id, CalendarTask.farm_id == farm_id
                    )
                )
            ).scalars().first()
            if not row:
                return False
            row.done = 1 if done else 0
            await s.commit()
            return True

    async def delete_task(self, farm_id: str, task_id: int) -> bool:
        """Delete one task (farm-scoped). Used to remove consult-added plan steps."""
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(CalendarTask).where(
                        CalendarTask.id == task_id, CalendarTask.farm_id == farm_id
                    )
                )
            ).scalars().first()
            if not row:
                return False
            await s.delete(row)
            await s.commit()
            return True

    async def mark_task_notified(self, task_id: int, on_date: str) -> None:
        async with SessionLocal() as s:
            row = (
                await s.execute(select(CalendarTask).where(CalendarTask.id == task_id))
            ).scalars().first()
            if row:
                row.notified_on = on_date
                await s.commit()

    async def context_blob(self, farm_id: str, farm: dict[str, Any] | None = None) -> str:
        """Farm + recent activity as a JSON blob for agent prompts.

        Pass `farm` if you already hold it - callers almost always do, and without
        it this re-queries the same row for nothing.
        """
        import json

        if farm is None:
            farm = await self.get_farm(farm_id)
        events = await self.recent_events(6, farm_id)
        return json.dumps({"farm": farm, "recent_activity": events}, ensure_ascii=False)


memory = FarmMemory()
