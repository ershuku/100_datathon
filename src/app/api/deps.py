from __future__ import annotations

from fastapi import Request

from app.api.errors import ApiError
from app.config import Settings
from app.jobs.service import JobService
from app.jobs.store import JobRecord


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_service(request: Request) -> JobService:
    return request.app.state.service


def require_job(service: JobService, job_id: str) -> JobRecord:
    rec = service.get(job_id)
    if rec is None:
        raise ApiError(404, "job_not_found", "Job not found")
    return rec
