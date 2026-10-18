"""Service configuration, read once from environment variables (and an optional .env file)."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class PipelineMode(str, Enum):
    DUMMY = "dummy"
    REAL = "real"


class TimeoutFallback(str, Enum):
    # TODO(team): decide the jury-facing behaviour when the deadline is hit.
    # "failed"  -> status=failed, error="timeout" (honest; counts as unprocessed)
    # "partial" -> status=done with the events the analyzer reported before the deadline
    #              (only meaningful if the real pipeline streams events; dummy does).
    FAILED = "failed"
    PARTIAL = "partial"


class ReviewPolicy(str, Enum):
    # TODO(team): events the analyzer marks needs_review ("review required" in Aibar.md).
    # "report" -> treat as violations (FAQ 16: a miss is unacceptable)
    # "drop"   -> exclude them from both UI and API results
    REPORT = "report"
    DROP = "drop"


class TrustProxy(str, Enum):
    NONE = "none"  # uvicorn is reached directly: use the socket address
    CLOUDFLARE = "cloudflare"  # behind Cloudflare Tunnel: CF-Connecting-IP
    XFF = "xff"  # behind Caddy: right-most X-Forwarded-For hop


WEAK_KEYS = {"change-me", "changeme", "secret", "test", "dev-key"}
MIN_KEY_LENGTH = 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: str = Field(min_length=1, description="Comma-separated list of accepted X-API-Key values")

    pipeline: PipelineMode = PipelineMode.DUMMY
    pipeline_factory: str = Field(
        default="pipeline.analyzer:create_analyzer",
        description="'module:callable' returning an object with analyze_video(); used when PIPELINE=real",
    )
    data_dir: Path = REPO_ROOT / "data"
    rules_path: Path = REPO_ROOT / "config" / "rules_legal.yaml"
    static_dir: Path = REPO_ROOT / "frontend" / "dist"

    max_upload_mb: int = Field(default=300, gt=0)
    min_duration_sec: float = Field(default=1.0, ge=0)
    max_duration_sec: float = Field(default=600.0, gt=0)

    job_timeout_sec: float = Field(default=280.0, gt=0, description="Total budget incl. queue wait")
    evidence_reserve_sec: float = Field(default=20.0, ge=0, description="Kept back for frames + JSON")
    max_violations: int = Field(default=20, ge=1, description="Events beyond this are dropped (by time)")
    min_analyze_sec: float = Field(default=10.0, ge=0, description="Below this budget the job fails at once")
    timeout_fallback: TimeoutFallback = TimeoutFallback.FAILED
    review_policy: ReviewPolicy = ReviewPolicy.REPORT

    worker_concurrency: int = Field(default=1, ge=1, le=8)
    max_queue: int = Field(default=20, ge=1, description="Queued+running jobs before 503")
    api_reserved_slots: int = Field(default=8, ge=0, description="Queue slots the anonymous UI may not use")
    ui_max_active: int = Field(default=2, ge=1, description="Max UI jobs queued+running at once")
    max_concurrent_uploads: int = Field(default=3, ge=1)
    min_free_disk_mb: int = Field(default=1024, ge=0)
    max_video_side_px: int = Field(default=4096, gt=0)
    max_fps: float = Field(default=240.0, gt=0)
    file_ttl_sec: int = Field(default=3600, ge=0)
    janitor_interval_sec: float = Field(default=60.0, gt=0)

    ui_upload_per_min: int = Field(default=6, ge=1)
    ui_poll_per_min: int = Field(default=120, ge=1)
    trust_proxy: TrustProxy = TrustProxy.NONE

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    video_encoder: str = "libx264"
    video_preset: str = "veryfast"
    video_crf: int = Field(default=23, ge=0, le=51)
    normalize_max_side: int = Field(default=1280, ge=0, description="0 = keep original size")
    pipeline_frames_fps: float = Field(default=0.0, ge=0, description="0 = do not pre-extract frames")

    evidence_max_side: int = Field(default=1280, gt=0)
    evidence_jpeg_quality: int = Field(default=85, ge=30, le=95)
    evidence_max_bytes: int = Field(default=300_000, gt=10_000)

    dummy_delay_sec: float = Field(default=8.0, ge=0)
    dummy_scenario: str = "auto"  # auto | none | violations | review | slow | crash

    enable_docs: bool = False
    log_level: str = "INFO"

    @field_validator("api_key")
    @classmethod
    def _keys_not_blank(cls, value: str) -> str:
        keys = [k.strip() for k in value.split(",") if k.strip()]
        if not keys:
            raise ValueError("API_KEY must contain at least one non-empty key")
        weak = [k for k in keys if k.lower() in WEAK_KEYS or len(k) < MIN_KEY_LENGTH]
        if weak:
            raise ValueError(f"API_KEY contains a weak key (placeholder or shorter than {MIN_KEY_LENGTH} chars)")
        return value

    @property
    def api_keys(self) -> tuple[str, ...]:
        return tuple(k.strip() for k in self.api_key.split(",") if k.strip())

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
