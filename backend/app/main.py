"""KrishiMitra AI - FastAPI entrypoint."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core import http
from app.core.config import settings
from app.core.db import dispose_engine
from app.core.fireworks import fireworks
from app.services import monitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("krishimitra")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open the shared HTTP clients here (not at import) so they bind to the running
    # loop; calls then reuse warm TLS connections instead of handshaking each time.
    await fireworks.startup()
    await http.startup()

    task: asyncio.Task | None = None
    if settings.monitor_enabled:
        logger.info("Starting autonomous monitor (every %sh)", settings.monitor_interval_hours)
        task = asyncio.create_task(monitor.loop())
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    # Close HTTP before the DB engine: in-flight calls may still write on the way down.
    await fireworks.aclose()
    await http.aclose()
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
    # Expose Server-Timing so the browser can read it cross-origin. Without this
    # the header is invisible to JS and upload time can't be isolated.
    expose_headers=["Server-Timing"],
)


@app.middleware("http")
async def server_timing(request: Request, call_next):
    """Emit `Server-Timing: app;dur=<ms>`.

    Lets the frontend subtract server time from total wall time to isolate upload
    time - the number that tells us whether the bottleneck is the network (big
    photo) or the AI. Cheap enough to leave on permanently.
    """
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    return response


app.include_router(router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": "/api/health"}
