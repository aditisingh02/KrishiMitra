"""One-off import of the legacy SQLite farm store into PostgreSQL.

Reads the old `data/krishimitra.db` (farms / events / notifications) and inserts
it into the configured Postgres database via the current ORM models, promoting
phone/language/lat/lon out of the JSON blob into indexed columns. The `memories`
table starts empty; run a couple of consults/diagnoses to populate it, or extend
this script to backfill embeddings from past events.

Usage (from backend/, with DATABASE_URL set and `alembic upgrade head` done):
    python -m scripts.migrate_sqlite_to_pg [path/to/krishimitra.db]
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

from app.core.config import settings
from app.core.db import SessionLocal, dispose_engine
from app.services.memory import Event, Farm, Notification, _norm_phone


def _rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    try:
        return conn.execute(f"SELECT * FROM {table}").fetchall()
    except sqlite3.OperationalError:
        return []  # table doesn't exist in the old db


async def main(db_path: str) -> None:
    src = Path(db_path)
    if not src.exists():
        print(f"SQLite file not found: {src}")
        return

    conn = sqlite3.connect(src)
    conn.row_factory = sqlite3.Row

    farms = _rows(conn, "farms")
    events = _rows(conn, "events")
    notifs = _rows(conn, "notifications")

    async with SessionLocal() as s:
        for r in farms:
            data = json.loads(r["data"])
            s.add(
                Farm(
                    id=r["id"],
                    phone=_norm_phone(data.get("phone")),
                    language=data.get("language"),
                    lat=data.get("lat"),
                    lon=data.get("lon"),
                    data=data,
                    created_at=r["updated_at"],
                    updated_at=r["updated_at"],
                )
            )
        for r in events:
            s.add(
                Event(
                    farm_id=r["farm_id"],
                    kind=r["kind"],
                    summary=r["summary"],
                    detail=json.loads(r["detail"] or "{}"),
                    created_at=r["created_at"],
                )
            )
        for r in notifs:
            s.add(
                Notification(
                    farm_id=r["farm_id"],
                    level=r["level"],
                    title=r["title"],
                    body=r["body"],
                    read=r["read"],
                    created_at=r["created_at"],
                )
            )
        await s.commit()

    conn.close()
    print(
        f"Imported {len(farms)} farms, {len(events)} events, {len(notifs)} notifications "
        f"into {settings.async_database_url.rsplit('@', 1)[-1]}"
    )
    await dispose_engine()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else settings.db_path
    asyncio.run(main(path))
