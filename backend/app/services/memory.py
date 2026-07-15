"""Farm Memory Agent - the digital twin store.

Acts as a CRM for the farm: crops, soil, disease history, treatments and a
running activity log. Backed by SQLite so the demo runs with zero setup.
The public surface is intentionally small so it can be swapped for Postgres.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FarmMemory:
    def __init__(self, db_path: str | None = None) -> None:
        self.path = Path(db_path or settings.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with _LOCK, self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS farms (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    farm_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    farm_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                """
            )

    # ---------- farm twin (farm_id == authenticated Clerk user id) ----------
    def get_farm(self, farm_id: str) -> dict[str, Any]:
        with _LOCK, self._conn() as c:
            row = c.execute("SELECT data FROM farms WHERE id=?", (farm_id,)).fetchone()
        return json.loads(row["data"]) if row else {}

    def farm_exists(self, farm_id: str) -> bool:
        with _LOCK, self._conn() as c:
            row = c.execute("SELECT 1 FROM farms WHERE id=?", (farm_id,)).fetchone()
        return row is not None

    def all_farms(self) -> list[dict[str, Any]]:
        with _LOCK, self._conn() as c:
            rows = c.execute("SELECT data FROM farms").fetchall()
        return [json.loads(r["data"]) for r in rows]

    def farm_by_phone(self, phone: str) -> dict[str, Any] | None:
        """Match an inbound WhatsApp number (suffix match tolerates +91/whatsapp: prefixes)."""
        digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
        if not digits:
            return None
        for farm in self.all_farms():
            fp = "".join(ch for ch in str(farm.get("phone", "")) if ch.isdigit())
            if fp and fp[-10:] == digits:
                return farm
        return None

    def save_farm(self, farm: dict[str, Any], farm_id: str) -> dict[str, Any]:
        farm = {**farm, "id": farm_id}
        with _LOCK, self._conn() as c:
            c.execute(
                "INSERT INTO farms(id,data,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (farm_id, json.dumps(farm), _now()),
            )
        return farm

    def update_farm(self, patch: dict[str, Any], farm_id: str) -> dict[str, Any]:
        farm = self.get_farm(farm_id)
        farm.update(patch)
        return self.save_farm(farm, farm_id)

    # ---------- events / history ----------
    def add_event(
        self,
        kind: str,
        summary: str,
        detail: dict[str, Any] | None,
        farm_id: str,
    ) -> None:
        with _LOCK, self._conn() as c:
            c.execute(
                "INSERT INTO events(farm_id,kind,summary,detail,created_at) VALUES(?,?,?,?,?)",
                (farm_id, kind, summary, json.dumps(detail or {}), _now()),
            )

    def recent_events(self, limit: int, farm_id: str) -> list[dict[str, Any]]:
        with _LOCK, self._conn() as c:
            rows = c.execute(
                "SELECT kind,summary,detail,created_at FROM events "
                "WHERE farm_id=? ORDER BY id DESC LIMIT ?",
                (farm_id, limit),
            ).fetchall()
        return [
            {
                "kind": r["kind"],
                "summary": r["summary"],
                "detail": json.loads(r["detail"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def record_disease(self, disease: str, crop: str, farm_id: str) -> None:
        farm = self.get_farm(farm_id)
        history = farm.get("recent_diseases", [])
        entry = {"disease": disease, "crop": crop, "date": _now()[:10]}
        history = [entry] + [h for h in history if h.get("disease") != disease][:9]
        self.update_farm({"recent_diseases": history}, farm_id)
        self.add_event("diagnosis", f"{disease} detected on {crop}", entry, farm_id)

    # ---------- notifications ----------
    def add_notification(self, farm_id: str, level: str, title: str, body: str) -> int:
        with _LOCK, self._conn() as c:
            cur = c.execute(
                "INSERT INTO notifications(farm_id,level,title,body,read,created_at) "
                "VALUES(?,?,?,?,0,?)",
                (farm_id, level, title, body, _now()),
            )
            return cur.lastrowid

    def list_notifications(self, farm_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with _LOCK, self._conn() as c:
            rows = c.execute(
                "SELECT id,level,title,body,read,created_at FROM notifications "
                "WHERE farm_id=? ORDER BY id DESC LIMIT ?",
                (farm_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def unread_count(self, farm_id: str) -> int:
        with _LOCK, self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) n FROM notifications WHERE farm_id=? AND read=0", (farm_id,)
            ).fetchone()
        return row["n"]

    def mark_notifications_read(self, farm_id: str) -> None:
        with _LOCK, self._conn() as c:
            c.execute("UPDATE notifications SET read=1 WHERE farm_id=?", (farm_id,))

    def notification_exists_today(self, farm_id: str, title: str) -> bool:
        with _LOCK, self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM notifications WHERE farm_id=? AND title=? AND substr(created_at,1,10)=? LIMIT 1",
                (farm_id, title, _now()[:10]),
            ).fetchone()
        return row is not None

    # ---------- compact context for prompts ----------
    def context_blob(self, farm_id: str) -> str:
        farm = self.get_farm(farm_id)
        events = self.recent_events(6, farm_id)
        return json.dumps({"farm": farm, "recent_activity": events}, ensure_ascii=False)


memory = FarmMemory()
