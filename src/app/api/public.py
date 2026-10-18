"""Public jury API (§10). X-API-Key is enforced by ApiKeyMiddleware before these handlers run."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.deps import get_service, get_settings_dep
from app.api.errors import ApiError
from app.api.upload import accept_upload
from app.config import Settings
from app.jobs.service import SOURCE_API, JobService
from app.schemas.public import AnalyzeResponse, JobDone, JobFailed, JobProcessing

router = APIRouter(prefix="/api/v1", tags=["public"])
NO_STORE = {"Cache-Control": "no-store"}


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    service: JobService = Depends(get_service),
) -> AnalyzeResponse:
    job_id = await accept_upload(request, settings, service, source=SOURCE_API)
    return AnalyzeResponse(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobDone | JobFailed | JobProcessing)
async def get_job(job_id: str, service: JobService = Depends(get_service)) -> JSONResponse:
    # Serialize the exact model ourselves so union coercion can never reshape the strict contract.
    body = await asyncio.to_thread(service.public_body, job_id)  # first build parses MBs of base64
    if body is None:
        raise ApiError(404, "job_not_found", "Job not found")
    return JSONResponse(body, headers=NO_STORE)
