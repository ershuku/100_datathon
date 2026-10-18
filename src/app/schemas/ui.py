"""Internal UI models. Extra fields are allowed here (never sent on /api/v1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LegalRefOut(BaseModel):
    document: str
    punkt: str
    rule_text: str | None = None
    url: str | None = None


class UiFrame(BaseModel):
    timestamp_sec: float
    url: str


class UiViolation(BaseModel):
    type: str
    type_code: str
    timecode_sec: float
    description: str
    legal_ref: LegalRefOut | None
    needs_review: bool
    evidence_frames: list[UiFrame]


class UiTimings(BaseModel):
    queue_wait_sec: float | None
    processing_sec: float | None
    total_sec: float | None


class UiVideo(BaseModel):
    duration_sec: float | None
    fps: float | None
    width: int | None
    height: int | None
    preview_url: str | None


class UiJob(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "done", "failed"]
    stage: str
    stage_text: str
    progress: int
    queue_position: int | None
    error: str | None
    error_code: str | None
    timings: UiTimings
    video: UiVideo
    verdict: Literal["violation", "no_violation"] | None
    partial: bool
    violations: list[UiViolation]
    result_url: str | None


class UiConfig(BaseModel):
    pipeline: str
    max_upload_mb: int
    poll_interval_ms: int
