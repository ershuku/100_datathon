"""Upload intake shared by /api/v1/analyze and /ui/analyze: validate, store, probe, submit."""

from __future__ import annotations

import asyncio
import secrets
import shutil
import time
from pathlib import Path

from fastapi import Request
from starlette.datastructures import UploadFile

from app.api.errors import ApiError
from app.config import Settings
from app.jobs.service import JobService, QueueFullError
from app.media.probe import MediaError, probe_video

ALLOWED_EXTENSION = ".mov"
CHUNK_BYTES = 1024 * 1024
QUEUE_FULL_RETRY_SEC = 30
_UNSUPPORTED = {"unsupported_container", "unsupported_resolution", "unsupported_frame_rate"}

async def _save(upload: UploadFile, dst: Path, max_bytes: int) -> int:
    size = 0
    with dst.open("wb") as out:
        while chunk := await upload.read(CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                raise ApiError(413, "file_too_large", "File too large")
            await asyncio.to_thread(out.write, chunk)  # keep the event loop free for jury polls
    return size


def _check_disk(settings: Settings) -> None:
    free = shutil.disk_usage(settings.data_dir).free
    if free < settings.min_free_disk_mb * 1024 * 1024 + 2 * settings.max_upload_bytes:
        raise ApiError(503, "storage_full", "Service is out of disk space, retry later",
                       headers={"Retry-After": str(QUEUE_FULL_RETRY_SEC)})  # fmt: skip


async def accept_upload(request: Request, settings: Settings, service: JobService, *, source: str) -> str:
    received_at = time.time()  # the job deadline includes upload time
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise ApiError(400, "not_multipart", "Expected multipart/form-data with a 'file' field")
    uploads = settings.data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    # Caps concurrent uploads (each spools to disk and runs ffprobe). Waiting requests have not had
    # their body read yet, so a burst of jury uploads just queues here briefly.
    async with service.upload_slots:
        _check_disk(settings)
        tmp = uploads / f"{secrets.token_hex(8)}.mov"
        try:
            return await _receive(request, settings, service, tmp, source=source, received_at=received_at)
        finally:
            tmp.unlink(missing_ok=True)


async def _receive(
    request: Request, settings: Settings, service: JobService, tmp: Path, *, source: str, received_at: float
) -> str:
    form = await request.form(max_files=1, max_fields=10)
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise ApiError(400, "missing_file", "Form field 'file' is required")
        if not (upload.filename or "").lower().endswith(ALLOWED_EXTENSION):
            raise ApiError(415, "unsupported_extension", "Only .mov files are accepted")
        size = await _save(upload, tmp, settings.max_upload_bytes)
    finally:
        await form.close()
    if size == 0:
        raise ApiError(400, "empty_file", "Uploaded file is empty")

    try:
        info = await asyncio.to_thread(probe_video, settings.ffprobe_bin, tmp,
                                       max_side_px=settings.max_video_side_px, max_fps=settings.max_fps)  # fmt: skip
    except MediaError as exc:
        raise ApiError(415 if exc.code in _UNSUPPORTED else 422, exc.code, exc.message) from exc
    if not settings.min_duration_sec <= info.duration_sec <= settings.max_duration_sec:
        raise ApiError(422, "duration_out_of_range",
                       f"Video duration must be {settings.min_duration_sec:g}-{settings.max_duration_sec:g} s")  # fmt: skip
    try:
        return service.submit(tmp, info, source=source, received_at=received_at)
    except QueueFullError as exc:
        raise ApiError(503, "queue_full", "Service is busy, retry later",
                       headers={"Retry-After": str(QUEUE_FULL_RETRY_SEC)}) from exc  # fmt: skip
