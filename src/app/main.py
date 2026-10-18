"""FastAPI app factory. Run: uvicorn app.main:app --app-dir src"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.analysis.legal import LegalCatalog
from app.api import health, public, ui
from app.api.errors import install_error_handlers
from app.api.guards import (
    ApiKeyMiddleware,
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
    UiRateLimitMiddleware,
)
from app.config import Settings, get_settings
from app.jobs.janitor import run_expiry, run_janitor, sweep
from app.jobs.processor import JobProcessor
from app.jobs.service import JobService
from app.jobs.store import JobStore
from app.jobs.worker import JobWorker
from app.logs import configure_logging, get_logger

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        store = JobStore(settings.db_path)
        interrupted = store.fail_interrupted(finished_at=time.time())
        if interrupted:
            log.warning("jobs_interrupted_by_restart", extra={"count": len(interrupted)})
        catalog = LegalCatalog.load(settings.rules_path)
        worker = JobWorker(settings, JobProcessor(settings, store, catalog), store)
        await worker.start()
        app.state.settings = settings
        app.state.store = store
        app.state.worker = worker
        app.state.service = JobService(settings, store, worker)
        await asyncio.to_thread(sweep, settings, store)
        background = [asyncio.create_task(run_janitor(settings, store), name="janitor"),
                      asyncio.create_task(run_expiry(settings, store), name="expiry")]  # fmt: skip
        log.info("service_started", extra={"pipeline": settings.pipeline.value, "slots": settings.worker_concurrency})
        try:
            yield
        finally:
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)
            await worker.stop()
            store.close()

    docs = settings.enable_docs
    app = FastAPI(
        title="Cashier video checker",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    install_error_handlers(app)
    # Starlette runs the last-added middleware first: headers -> auth -> size limit -> UI rate limit -> app.
    app.add_middleware(
        UiRateLimitMiddleware,
        uploads_per_min=settings.ui_upload_per_min,
        reads_per_min=settings.ui_poll_per_min,
        trust_proxy=settings.trust_proxy,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
    app.add_middleware(ApiKeyMiddleware, keys=settings.api_keys)
    app.add_middleware(SecurityHeadersMiddleware)  # outermost: also covers 401/413/429 responses

    app.include_router(health.router)
    app.include_router(public.router)
    app.include_router(ui.router)
    if settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


def __getattr__(name: str):  # lazy so tests can build apps with their own settings
    if name == "app":
        return create_app()
    raise AttributeError(name)
