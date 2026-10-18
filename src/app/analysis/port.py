"""Backend-side seam to the ML analyzer.

PROVISIONAL: the final interface with the ML team (Aibar) is not agreed yet. This file is the
only place that has to change when it is. It follows TEAM_PLAN §15: the backend passes a local
video path plus a job context; the analyzer returns events with type, timecode, description,
1-3 evidence moments and an optional rule_id. The backend owns JPEG/base64, legal text lookup
and the public JSON.

Everything here must be picklable: the analyzer runs in a separate process so a stuck model can
be killed at the deadline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class EvidenceRef:
    """One evidence moment. If the analyzer already chose the exact frame, it passes image_path
    (a file it wrote under ctx.work_dir) so the backend does not re-extract by approximate time."""

    timestamp_sec: float
    image_path: str | None = None


@dataclass(frozen=True)
class DetectedEvent:
    type_code: str  # key into config/rules_legal.yaml, e.g. "SAFE"
    timecode_sec: float  # seconds from the start of the video
    description: str  # what is visible and why it may be a violation (RU), no legal text
    evidence: tuple[EvidenceRef, ...]  # 1-3 items
    rule_id: str | None = None  # optional, overrides the type's default legal reference
    needs_review: bool = False  # "review required" outcome (see Aibar.md); handled by REVIEW_POLICY
    type_name: str | None = None  # fallback display name for codes missing from the YAML


@dataclass(frozen=True)
class AnalyzerOutput:
    events: tuple[DetectedEvent, ...]
    debug: dict[str, Any] = field(default_factory=dict)  # stored internally, never shown publicly


@dataclass(frozen=True)
class JobContext:
    job_id: str
    duration_sec: float
    fps: float
    width: int  # after rotation
    height: int
    source_path: str  # untouched original upload (rotation NOT applied; same timeline)
    work_dir: str  # scratch dir the analyzer may write to; deleted with the job files
    time_budget_sec: float  # how long the analyzer has before it is killed
    frames_dir: str | None = None  # pre-extracted JPEGs if PIPELINE_FRAMES_FPS > 0
    frames_fps: float = 0.0  # file N (1-based) is at (N - 1) / frames_fps seconds


class Reporter(Protocol):
    def progress(self, percent: int, stage: str) -> None:
        """percent 0-100 within the analysis stage; stage is short RU text for the UI."""

    def event(self, event: DetectedEvent) -> None:
        """Optional: report an event as soon as it is found (used by TIMEOUT_FALLBACK=partial)."""


class Analyzer(Protocol):
    def analyze_video(self, video_path: str, ctx: JobContext, reporter: Reporter) -> AnalyzerOutput: ...


class AnalyzerError(Exception):
    """Raised by the runner when the analyzer crashed or returned something invalid."""


class AnalyzerTimeout(Exception):
    def __init__(self, partial_events: tuple[DetectedEvent, ...]) -> None:
        super().__init__("analyzer exceeded its time budget")
        self.partial_events = partial_events
