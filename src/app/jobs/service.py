"""Service layer shared by the public API and the UI routes."""

from __future__ import annotations

import asyncio
import secrets
import shutil
import time
from collections import OrderedDict
from pathlib import Path

from app.config import Settings
from app.jobs.files import job_files
from app.jobs.store import DONE, FAILED, JobRecord, JobStore
from app.jobs.worker import SOURCE_API, SOURCE_UI, JobWorker
from app.logs import get_logger
from app.media.probe import VideoInfo
from app.results import public_view

log = get_logger(__name__)

JOB_ID_BYTES = 8  # 16 hex chars, not guessable
CACHE_SIZE = 64


class QueueFullError(Exception):
    pass


def is_valid_job_id(job_id: str) -> bool:
    return len(job_id) == JOB_ID_BYTES * 2 and all(c in "0123456789abcdef" for c in job_id)


class JobService:
    def __init__(self, settings: Settings, store: JobStore, worker: JobWorker) -> None:
        self.settings = settings
        self.store = store
        self.worker = worker
        self._public_cache: OrderedDict[str, dict] = OrderedDict()
        self._record_cache: OrderedDict[str, JobRecord] = OrderedDict()
        self.upload_slots = asyncio.Semaphore(settings.max_concurrent_uploads)  # built inside the app loop

    def public_body(self, job_id: str) -> dict | None:
        """Public JSON for a job, None if unknown. Finished jobs never change, so their (large) body
        is cached instead of loading and re-parsing megabytes of base64 frames on every poll."""
        cached = self._public_cache.get(job_id)
        if cached is not None:
            self._public_cache.move_to_end(job_id)
            return cached
        rec = self.get(job_id)
        if rec is None:
            return None
        body = public_view(rec).model_dump(mode="json")
        if rec.status in (DONE, FAILED):
            _remember(self._public_cache, rec.id, body)
        return body

    def _has_room(self, source: str) -> bool:
        """The jury API may use the whole queue. The anonymous UI may neither take the last
        API_RESERVED_SLOTS slots nor have more than UI_MAX_ACTIVE jobs at once (API jobs also run
        first, see JobWorker)."""
        if source == SOURCE_API:
            return self.store.count_active() < self.settings.max_queue
        ui_cap = max(1, self.settings.max_queue - self.settings.api_reserved_slots)
        return (self.store.count_active() < ui_cap
                and self.store.count_active(SOURCE_UI) < self.settings.ui_max_active)  # fmt: skip

    def submit(self, upload_tmp: Path, info: VideoInfo, *, source: str, received_at: float | None = None) -> str:
        """received_at: when the request started — the deadline counts from there (incl. upload)."""
        if not self._has_room(source):
            raise QueueFullError
        job_id = secrets.token_hex(JOB_ID_BYTES)
        files = job_files(self.settings.jobs_dir, job_id)
        files.root.mkdir(parents=True, exist_ok=False)
        try:
            shutil.move(str(upload_tmp), files.upload)
            width, height = info.display_size
            meta = {**info.to_dict(), "display_width": width, "display_height": height, "source": source}
            self.store.create(job_id, created_at=received_at or time.time(), video_meta=meta, source=source)
        except Exception:
            files.remove_all()
            raise
        self.worker.enqueue(job_id, source)
        log.info("job_submitted", extra={
            "job_id": job_id, "duration_sec": round(info.duration_sec, 2), "fps": round(info.fps, 2),
            "codec": info.codec, "rotation": info.rotation, "queue_length": self.worker.queue_length,
            "source": source,
        })  # fmt: skip
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        """Finished jobs never change (file presence is checked on disk, see preview_path), so their
        parsed record is cached instead of re-parsing base64 frames on every request."""
        if not is_valid_job_id(job_id):
            return None
        cached = self._record_cache.get(job_id)
        if cached is not None:
            self._record_cache.move_to_end(job_id)
            return cached
        rec = self.store.get(job_id)
        if rec is not None and rec.status in (DONE, FAILED):
            _remember(self._record_cache, job_id, rec)
        return rec

    def preview_path(self, rec: JobRecord) -> Path | None:
        if rec.files_deleted:
            return None
        path = job_files(self.settings.jobs_dir, rec.id).normalized
        return path if rec.status == "done" and path.exists() else None


def _remember(cache: OrderedDict, key: str, value: object) -> None:
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > CACHE_SIZE:
        cache.popitem(last=False)
