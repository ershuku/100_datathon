"""In-process job scheduler: N asyncio slots, each owning one analyzer child process.

Jury (API) jobs always run before UI jobs: a free slot takes the oldest API job first, so
anonymous UI traffic can delay the jury by at most the UI jobs already running.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

from app.analysis.runner import AnalyzerProcess
from app.config import PipelineMode, Settings
from app.jobs.processor import JobProcessor
from app.jobs.store import FAILED, JobStore
from app.logs import get_logger

log = get_logger(__name__)

STOP_WAIT_SEC = 10.0
DUMMY_FACTORY = "app.analysis.dummy:DummyAnalyzer"
SOURCE_API, SOURCE_UI = "api", "ui"


def analyzer_spec(settings: Settings) -> tuple[str, dict]:
    if settings.pipeline is PipelineMode.DUMMY:
        return DUMMY_FACTORY, {"delay_sec": settings.dummy_delay_sec, "scenario": settings.dummy_scenario}
    return settings.pipeline_factory, {}


class JobWorker:
    def __init__(self, settings: Settings, processor: JobProcessor, store: JobStore) -> None:
        self._settings = settings
        self._processor = processor
        self._store = store
        self._pending: dict[str, deque[str]] = {SOURCE_API: deque(), SOURCE_UI: deque()}
        self._wakeup = asyncio.Event()
        self._running: set[str] = set()
        self._threads: set[asyncio.Future] = set()
        self._tasks: list[asyncio.Task] = []
        self._analyzers: list[AnalyzerProcess] = []

    async def start(self) -> None:
        spec, kwargs = analyzer_spec(self._settings)
        for i in range(self._settings.worker_concurrency):
            analyzer = AnalyzerProcess(spec, kwargs, name=f"analyzer-{i}")
            await asyncio.to_thread(analyzer.start)
            self._analyzers.append(analyzer)
            self._tasks.append(asyncio.create_task(self._slot_loop(analyzer), name=f"job-slot-{i}"))
        log.info("worker_started", extra={"slots": len(self._tasks), "pipeline": self._settings.pipeline.value})

    async def stop(self) -> None:
        for analyzer in self._analyzers:
            analyzer.close()  # no restarts from here on, even if a job thread asks for one
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        # Killing the analyzers unblocks any job thread waiting on them; then let those threads
        # finish writing before the store is closed.
        await asyncio.gather(*(asyncio.to_thread(a.stop) for a in self._analyzers))
        if self._threads:
            await asyncio.wait(self._threads, timeout=STOP_WAIT_SEC)
        self._tasks.clear()
        self._analyzers.clear()

    def enqueue(self, job_id: str, source: str = SOURCE_API) -> None:
        self._pending[SOURCE_UI if source == SOURCE_UI else SOURCE_API].append(job_id)
        self._wakeup.set()

    def position(self, job_id: str) -> int | None:
        """1-based place among jobs waiting for a slot, in the order they will run; None if not waiting."""
        api, ui = self._pending[SOURCE_API], self._pending[SOURCE_UI]
        if job_id in api:
            return api.index(job_id) + 1
        if job_id in ui:
            return len(api) + ui.index(job_id) + 1
        return None

    @property
    def queue_length(self) -> int:
        return sum(len(q) for q in self._pending.values())

    @property
    def running(self) -> int:
        return len(self._running)

    async def _next_job(self) -> str:
        while True:
            for source in (SOURCE_API, SOURCE_UI):
                if self._pending[source]:
                    return self._pending[source].popleft()
            self._wakeup.clear()
            await self._wakeup.wait()

    def _fail_best_effort(self, job_id: str) -> None:
        try:
            rec = self._store.get(job_id)
            if rec is not None and rec.status in ("queued", "processing"):
                self._store.update(job_id, status=FAILED, stage="failed", error="internal error",
                                   error_code="internal_error", finished_at=time.time())  # fmt: skip
        except Exception:  # noqa: BLE001
            log.exception("worker_fail_mark_error", extra={"job_id": job_id})

    async def _slot_loop(self, analyzer: AnalyzerProcess) -> None:
        while True:
            job_id = await self._next_job()
            self._running.add(job_id)
            future = asyncio.ensure_future(asyncio.to_thread(self._processor.process, job_id, analyzer))
            self._threads.add(future)
            future.add_done_callback(self._threads.discard)  # stays tracked until the thread really ends
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the slot alive whatever happens
                log.exception("worker_slot_error", extra={"job_id": job_id})
                self._fail_best_effort(job_id)
            finally:
                self._running.discard(job_id)
