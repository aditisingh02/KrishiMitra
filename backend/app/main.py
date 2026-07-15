"""KrishiMitra AI - FastAPI entrypoint."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.db import dispose_engine
from app.services import monitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("krishimitra")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task: asyncio.Task | None = None
    if settings.monitor_enabled:
        logger.info("Starting autonomous monitor (every %sh)", settings.monitor_interval_hours)
        task = asyncio.create_task(monitor.loop())
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await dispose_engine()


app = FastAPI(
    title=settings.app_name,
    description="Agentic Agronomy Operating System for Natural Farming",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": "/api/health"}
