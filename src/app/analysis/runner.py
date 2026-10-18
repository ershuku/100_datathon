"""Runs an analyzer in a long-lived child process.

The model loads once per process. If a job overruns its budget the process is killed and a fresh
one is started — a Python thread could not be stopped, so a stuck GPU call would block the queue.
"""

from __future__ import annotations

import contextlib
import importlib
import multiprocessing as mp
import queue
import threading
import time
import traceback
from collections.abc import Callable
from typing import Any

import psutil

from app.analysis.port import AnalyzerError, AnalyzerOutput, AnalyzerTimeout, DetectedEvent, JobContext
from app.logs import get_logger

log = get_logger(__name__)

POLL_SEC = 0.25
READY_TIMEOUT_SEC = 600.0  # model loading can be slow; it is not counted against a single job
SHUTDOWN_GRACE_SEC = 5.0
PARENT_CHECK_SEC = 1.0


def load_factory(spec: str) -> Callable[..., Any]:
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ValueError(f"factory spec must look like 'package.module:callable', got {spec!r}")
    return getattr(importlib.import_module(module_name), attr)


class _QueueReporter:
    def __init__(self, out: mp.Queue, job_id: str) -> None:
        self._out = out
        self._job_id = job_id

    def progress(self, percent: int, stage: str) -> None:
        self._out.put(("progress", self._job_id, (max(0, min(100, int(percent))), str(stage)[:120])))

    def event(self, event: DetectedEvent) -> None:
        self._out.put(("event", self._job_id, event))


def _child_main(factory_spec: str, factory_kwargs: dict, inbox: mp.Queue, outbox: mp.Queue) -> None:
    try:
        analyzer = load_factory(factory_spec)(**factory_kwargs)
    except Exception:  # noqa: BLE001 - reported to the parent, which marks jobs failed
        outbox.put(("load_error", None, traceback.format_exc(limit=5)))
        return
    outbox.put(("ready", None, None))
    parent = mp.parent_process()
    while True:
        try:
            msg = inbox.get(timeout=PARENT_CHECK_SEC)
        except queue.Empty:
            if parent is not None and not parent.is_alive():
                return  # the service died (e.g. kill -9): do not keep holding the GPU
            continue
        if msg is None:
            return
        job_id, video_path, ctx = msg
        try:
            result = analyzer.analyze_video(video_path, ctx, _QueueReporter(outbox, job_id))
            if not isinstance(result, AnalyzerOutput):
                raise TypeError(f"analyze_video must return AnalyzerOutput, got {type(result).__name__}")
            outbox.put(("result", job_id, result))
        except Exception as exc:  # noqa: BLE001
            # Type only: exception text from a model could describe video content.
            outbox.put(("error", job_id, type(exc).__name__))


def _kill_tree(pid: int | None) -> None:
    """Kill the analyzer and everything it spawned (ffmpeg, DataLoader workers)."""
    if pid is None:
        return
    try:
        parent = psutil.Process(pid)
        procs = [*parent.children(recursive=True), parent]
    except psutil.NoSuchProcess:
        return
    for proc in procs:
        with contextlib.suppress(psutil.NoSuchProcess):
            proc.kill()
    psutil.wait_procs(procs, timeout=SHUTDOWN_GRACE_SEC)


class AnalyzerProcess:
    """One analyzer slot. Not thread-safe: each worker slot owns exactly one instance."""

    def __init__(self, factory_spec: str, factory_kwargs: dict | None = None, name: str = "analyzer") -> None:
        self._spec = factory_spec
        self._kwargs = factory_kwargs or {}
        self._name = name
        self._ctx = mp.get_context("spawn")
        self._proc: mp.process.BaseProcess | None = None
        self._inbox: mp.Queue | None = None
        self._outbox: mp.Queue | None = None
        self._ready = threading.Event()
        self._started_at = 0.0
        self._closing = False
        self._lock = threading.RLock()  # start/kill may race between a job thread and shutdown

    def close(self) -> None:
        """Shutdown has begun: refuse any further (re)start."""
        self._closing = True

    def start(self) -> None:
        with self._lock:
            if self._closing:
                raise AnalyzerError("service is shutting down")
            self._start_locked()

    def _start_locked(self) -> None:
        self._close_queues()
        self._inbox, self._outbox = self._ctx.Queue(), self._ctx.Queue()
        self._ready.clear()
        self._started_at = time.monotonic()
        # Not a daemon: the analyzer may need its own children (DataLoader workers, ffmpeg).
        self._proc = self._ctx.Process(
            target=_child_main, args=(self._spec, self._kwargs, self._inbox, self._outbox), name=self._name
        )
        self._proc.start()
        log.info("analyzer_process_started", extra={"slot": self._name, "pid": self._proc.pid})

    def _wait_ready(self, timeout: float) -> None:
        if self._ready.is_set():
            return
        if time.monotonic() - self._started_at > READY_TIMEOUT_SEC:
            log.error("analyzer_load_timeout_restarting", extra={"slot": self._name})
            self.restart()
        assert self._outbox is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                kind, _, payload = self._outbox.get(timeout=POLL_SEC)
            except queue.Empty:
                if not self.is_alive():
                    raise AnalyzerError("analyzer process exited during startup") from None
                continue
            if kind == "ready":
                self._ready.set()
                return
            if kind == "load_error":
                log.error("analyzer_load_failed", extra={"slot": self._name, "detail": payload})
                raise AnalyzerError("analyzer failed to load")
        raise AnalyzerTimeout(())

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    def restart(self) -> None:
        with self._lock:
            self.kill()
            self.start()

    def kill(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.is_alive():
                _kill_tree(self._proc.pid)
                self._proc.join(SHUTDOWN_GRACE_SEC)
            self._proc = None
            self._ready.clear()

    def _close_queues(self) -> None:
        for q in (self._inbox, self._outbox):
            if q is not None:
                q.close()
                q.cancel_join_thread()
        self._inbox = self._outbox = None

    def stop(self) -> None:
        self._closing = True
        with self._lock:
            if self._proc is not None and self._proc.is_alive() and self._inbox is not None:
                self._inbox.put(None)
                self._proc.join(SHUTDOWN_GRACE_SEC)
            self.kill()
            self._close_queues()

    def run(
        self,
        video_path: str,
        ctx: JobContext,
        *,
        timeout_sec: float,
        on_progress: Callable[[int, str], None],
        on_event: Callable[[DetectedEvent], None],
    ) -> AnalyzerOutput:
        if not self.is_alive():
            self.start()
        deadline = time.monotonic() + timeout_sec
        # If the model is still loading at the deadline this raises AnalyzerTimeout and keeps loading.
        self._wait_ready(max(0.0, deadline - time.monotonic()))
        assert self._inbox is not None and self._outbox is not None
        self._inbox.put((ctx.job_id, video_path, ctx))
        partial: list[DetectedEvent] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                log.warning("analyzer_timeout_killing", extra={"slot": self._name, "job_id": ctx.job_id})
                self.restart()
                raise AnalyzerTimeout(tuple(partial))
            try:
                kind, job_id, payload = self._outbox.get(timeout=min(POLL_SEC, remaining))
            except queue.Empty:
                if not self.is_alive():
                    self.start()
                    raise AnalyzerError("analyzer process crashed") from None
                continue
            if job_id != ctx.job_id:
                continue
            if kind == "progress":
                on_progress(*payload)
            elif kind == "event":
                partial.append(payload)
                on_event(payload)
            elif kind == "result":
                return payload
            elif kind == "error":
                log.error("analyzer_error", extra={"slot": self._name, "job_id": job_id, "detail": payload})
                raise AnalyzerError("analyzer raised an error")
