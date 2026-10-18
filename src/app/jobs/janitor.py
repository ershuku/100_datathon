"""Deletes uploaded and derived video files FILE_TTL_SEC after a job finishes. JSON results stay."""

from __future__ import annotations

import asyncio
import shutil
import time

from app.config import Settings
from app.jobs.files import job_files
from app.jobs.store import JobStore
from app.logs import get_logger

log = get_logger(__name__)

STALE_UPLOAD_SEC = 3600
EXPIRY_INTERVAL_SEC = 5.0


def sweep(settings: Settings, store: JobStore, now: float | None = None) -> int:
    now = time.time() if now is None else now
    removed = 0
    for job_id in store.expired_file_jobs(finished_before=now - settings.file_ttl_sec):
        job_files(settings.jobs_dir, job_id).remove_all()
        store.update(job_id, files_deleted=1)
        removed += 1
    uploads = settings.data_dir / "uploads"
    if uploads.is_dir():  # temp files of requests that died mid-upload
        for tmp in uploads.iterdir():
            if now - tmp.stat().st_mtime > STALE_UPLOAD_SEC:
                if tmp.is_dir():
                    shutil.rmtree(tmp, ignore_errors=True)
                else:
                    tmp.unlink(missing_ok=True)
    if removed:
        log.info("janitor_removed_job_files", extra={"jobs": removed})
    return removed


async def run_janitor(settings: Settings, store: JobStore) -> None:
    while True:
        try:
            await asyncio.to_thread(sweep, settings, store)
        except Exception:  # noqa: BLE001 - never let cleanup crash the service
            log.exception("janitor_error")
        await asyncio.sleep(settings.janitor_interval_sec)


def expire_queued(settings: Settings, store: JobStore, now: float | None = None) -> list[str]:
    """Fail queued jobs whose whole budget is already gone, so the answer does not wait for a slot.
    The worker skips them later because claim() only takes jobs that are still queued."""
    now = time.time() if now is None else now
    ids = store.fail_expired_queued(created_before=now - settings.job_timeout_sec, finished_at=now)
    if ids:
        log.warning("queued_jobs_expired", extra={"count": len(ids)})
    return ids


async def run_expiry(settings: Settings, store: JobStore) -> None:
    while True:
        try:
            await asyncio.to_thread(expire_queued, settings, store)
        except Exception:  # noqa: BLE001
            log.exception("expiry_error")
        await asyncio.sleep(EXPIRY_INTERVAL_SEC)
