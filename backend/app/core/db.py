"""Async SQLAlchemy engine and session factory (Render PostgreSQL).

The engine is created lazily on first use so importing the app (e.g. for Alembic
autogeneration or tests) doesn't require a live database. Models declare against
`Base`; the memory service opens a short-lived `SessionLocal()` per operation,
which keeps the existing `memory.<method>()` call shape.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(
            settings.async_database_url,
            pool_pre_ping=True,
            future=True,
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def SessionLocal() -> AsyncSession:
    """Return a new AsyncSession (initialising the engine on first call)."""
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker()


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
