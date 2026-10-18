"""Public (jury) API models. Must match the case brief §10 exactly: no extra fields."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceFrame(_Strict):
    timestamp_sec: float = Field(ge=0)
    image_base64: str = Field(min_length=4, description="JPEG, plain base64, no data: prefix")


class Violation(_Strict):
    type: str = Field(min_length=1)
    timecode_sec: float = Field(ge=0)
    description: str = Field(min_length=1)
    evidence_frames: list[EvidenceFrame] = Field(min_length=1, max_length=3)


class AnalyzeResponse(_Strict):
    job_id: str


class JobProcessing(_Strict):
    job_id: str
    status: Literal["processing"] = "processing"


class JobFailed(_Strict):
    job_id: str
    status: Literal["failed"] = "failed"
    error: str


class JobDone(_Strict):
    job_id: str
    status: Literal["done"] = "done"
    verdict: Literal["violation", "no_violation"]
    violations: list[Violation]


PublicJob = JobProcessing | JobFailed | JobDone
