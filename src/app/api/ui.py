"""Same-origin routes for the web UI. No API key (FAQ: no auth for the UI); rate-limited by middleware.

The jury key never reaches the browser: these routes call the service layer directly.
"""

from __future__ import annotations

import asyncio
import base64

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.api.deps import get_service, get_settings_dep, require_job
from app.api.errors import ApiError
from app.api.upload import accept_upload
from app.config import Settings
from app.jobs.service import SOURCE_UI, JobService
from app.results import ui_view
from app.schemas.ui import UiConfig, UiJob

router = APIRouter(prefix="/ui", tags=["ui"])

POLL_INTERVAL_MS = 2000
NO_STORE = {"Cache-Control": "no-store"}  # confidential frames: never in browser or CDN caches


@router.get("/config", response_model=UiConfig)
async def ui_config(settings: Settings = Depends(get_settings_dep)) -> UiConfig:
    return UiConfig(pipeline=settings.pipeline.value, max_upload_mb=settings.max_upload_mb,
                    poll_interval_ms=POLL_INTERVAL_MS)  # fmt: skip


@router.post("/analyze")
async def ui_analyze(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    service: JobService = Depends(get_service),
) -> dict[str, str]:
    return {"job_id": await accept_upload(request, settings, service, source=SOURCE_UI)}


@router.get("/jobs/{job_id}", response_model=UiJob)
async def ui_job(job_id: str, service: JobService = Depends(get_service)) -> JSONResponse:
    rec = await asyncio.to_thread(require_job, service, job_id)
    view = ui_view(rec, queue_position=service.worker.position(job_id),
                   preview_available=service.preview_path(rec) is not None)  # fmt: skip
    return JSONResponse(view.model_dump(mode="json"), headers=NO_STORE)


@router.get("/jobs/{job_id}/preview.mp4")
async def ui_preview(job_id: str, service: JobService = Depends(get_service)) -> FileResponse:
    rec = await asyncio.to_thread(require_job, service, job_id)
    path = service.preview_path(rec)
    if path is None:
        raise ApiError(404, "preview_unavailable", "Preview is not available (not ready or already deleted)")
    return FileResponse(path, media_type="video/mp4", headers=NO_STORE)


@router.get("/jobs/{job_id}/frames/{vi}/{fi}.jpg")
async def ui_frame(job_id: str, vi: int, fi: int, service: JobService = Depends(get_service)) -> Response:
    rec = await asyncio.to_thread(require_job, service, job_id)
    violations = (rec.result or {}).get("violations", [])
    if not (0 <= vi < len(violations)) or not (0 <= fi < len(violations[vi]["frames"])):
        raise ApiError(404, "frame_not_found", "Frame not found")
    data = base64.b64decode(violations[vi]["frames"][fi]["jpeg_base64"])
    return Response(data, media_type="image/jpeg", headers=NO_STORE)


@router.get("/jobs/{job_id}/result.json")
async def ui_result_download(job_id: str, service: JobService = Depends(get_service)) -> JSONResponse:
    """The exact public-API JSON, offered as a download."""
    rec = await asyncio.to_thread(require_job, service, job_id)
    if rec.status != "done":
        raise ApiError(409, "not_done", "Result is not ready")
    headers = {"Content-Disposition": f'attachment; filename="result_{job_id}.json"', **NO_STORE}
    return JSONResponse(await asyncio.to_thread(service.public_body, job_id), headers=headers)
