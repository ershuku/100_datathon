"""Processes one job end to end inside the hard deadline (created_at + JOB_TIMEOUT_SEC).

normalize (0-20%) -> analyze (20-90%) -> evidence frames (90-100%) -> stored result.
Failures become status=failed with a short reason; they are never turned into no_violation.
"""

from __future__ import annotations

import math
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.analysis.legal import LegalCatalog
from app.analysis.port import AnalyzerError, AnalyzerOutput, AnalyzerTimeout, DetectedEvent, EvidenceRef, JobContext
from app.analysis.runner import AnalyzerProcess
from app.config import Settings, TimeoutFallback
from app.jobs.files import JobFiles, job_files
from app.jobs.store import DONE, FAILED, QUEUED, JobStore
from app.logs import get_logger
from app.media import evidence
from app.media.normalize import normalize_video
from app.media.probe import MediaError, VideoInfo, probe_video
from app.results import apply_review_policy, round1, stored_result, stored_violation

log = get_logger(__name__)

PROGRESS_WRITE_INTERVAL_SEC = 0.5
NORMALIZE_SPAN = (0, 20)
ANALYZE_SPAN = (20, 90)
EVIDENCE_SPAN = (90, 99)
FINALIZE_MARGIN_SEC = 2.0  # kept free after evidence for JSON + DB write
RETRY_OFFSET_SEC = 0.5  # second attempt for a frame that could not be decoded
EVIDENCE_TEXT = "Подготовка кадров-доказательств"


class _Progress:
    """Throttled progress writer so the analyzer can report as often as it likes."""

    def __init__(self, store: JobStore, job_id: str) -> None:
        self._store, self._job_id = store, job_id
        self._last = (-1, "", "", 0.0)

    def set(self, stage: str, text: str, percent: int, *, force: bool = False) -> None:
        last_pct, last_stage, last_text, last_t = self._last
        now = time.monotonic()
        changed = stage != last_stage or text != last_text
        if not force and not changed and (percent == last_pct or now - last_t < PROGRESS_WRITE_INTERVAL_SEC):
            return
        self._store.update(self._job_id, stage=stage, stage_text=text, progress=max(0, min(100, percent)))
        self._last = (percent, stage, text, now)


def _scale(span: tuple[int, int], fraction: float) -> int:
    lo, hi = span
    return int(lo + (hi - lo) * max(0.0, min(1.0, fraction)))


def _info_from_meta(meta: dict[str, Any]) -> VideoInfo:
    return VideoInfo(**{k: meta[k] for k in VideoInfo.__dataclass_fields__})


class _Deadline:
    """Wall-clock deadline (from created_at) converted once to the monotonic clock."""

    def __init__(self, wall_deadline: float) -> None:
        self._mono = time.monotonic() + (wall_deadline - time.time())

    def remaining(self) -> float:
        return self._mono - time.monotonic()

    @property
    def monotonic(self) -> float:
        return self._mono


class JobProcessor:
    def __init__(self, settings: Settings, store: JobStore, catalog: LegalCatalog) -> None:
        self.settings = settings
        self.store = store
        self.catalog = catalog

    # -- public -----------------------------------------------------------------------------

    def process(self, job_id: str, analyzer: AnalyzerProcess) -> None:
        rec = self.store.get(job_id)
        if rec is None or rec.status != QUEUED:
            return
        files = job_files(self.settings.jobs_dir, job_id)
        started = time.time()
        if not self.store.claim(job_id, started):
            return  # already answered (e.g. expired while queued)
        try:
            log.info("job_started", extra={"job_id": job_id, "queue_wait_sec": round(started - rec.created_at, 2)})
            deadline = _Deadline(rec.created_at + self.settings.job_timeout_sec)
            info = _info_from_meta(rec.video_meta or {})
            self._run(job_id, info, files, deadline, analyzer, _Progress(self.store, job_id))
        except MediaError as exc:
            self._fail(job_id, exc.code, exc.message)
        except AnalyzerError as exc:
            log.error("job_analyzer_error", extra={"job_id": job_id, "detail": str(exc)})
            self._fail(job_id, "analysis_failed", "analysis failed")
        except Exception:  # noqa: BLE001 - last line of defence, job must not stay "processing"
            log.exception("job_internal_error", extra={"job_id": job_id})
            self._fail(job_id, "internal_error", "internal error")
        finally:
            files.remove_upload()
            self._log_finished(job_id)

    # -- pipeline ---------------------------------------------------------------------------

    def _run(
        self, job_id: str, info: VideoInfo, files: JobFiles, deadline: _Deadline,
        analyzer: AnalyzerProcess, progress: _Progress,
    ) -> None:  # fmt: skip
        reserve = self.settings.evidence_reserve_sec
        # Not enough time left to do anything useful: answer now instead of starting work that
        # will be killed (killing the analyzer also costs the next job a model reload).
        if deadline.remaining() <= reserve + self.settings.min_analyze_sec:
            self._on_timeout(job_id, info, files, (), stage="queue")
            return

        progress.set("normalize", "Подготовка видео", NORMALIZE_SPAN[0], force=True)
        frames_dir = files.frames_dir if self.settings.pipeline_frames_fps > 0 else None
        t0 = time.monotonic()
        try:
            normalize_video(
                self.settings.ffmpeg_bin, files.upload, files.normalized,
                duration_sec=info.duration_sec, timeout_sec=deadline.remaining() - reserve,
                encoder=self.settings.video_encoder, preset=self.settings.video_preset, crf=self.settings.video_crf,
                max_side=self.settings.normalize_max_side,
                frames_dir=frames_dir, frames_fps=self.settings.pipeline_frames_fps,
                on_progress=lambda f: progress.set("normalize", "Подготовка видео", _scale(NORMALIZE_SPAN, f)),
            )  # fmt: skip
        except TimeoutError:
            self._on_timeout(job_id, info, files, (), stage="normalize")
            return
        # Clamp evidence to what is actually decodable (container duration can include longer audio).
        decoded = probe_video(self.settings.ffprobe_bin, files.normalized)
        info = replace(info, duration_sec=min(info.duration_sec, decoded.duration_sec))
        self._stage_done(job_id, "normalize", t0)

        if deadline.remaining() - reserve < self.settings.min_analyze_sec:
            self._on_timeout(job_id, info, files, (), stage="normalize")
            return
        files.work_dir.mkdir(parents=True, exist_ok=True)
        width, height = info.display_size
        ctx = JobContext(
            job_id=job_id, duration_sec=info.duration_sec, fps=info.fps, width=width, height=height,
            source_path=str(files.upload), work_dir=str(files.work_dir),
            time_budget_sec=max(0.0, deadline.remaining() - reserve),
            frames_dir=str(frames_dir) if frames_dir else None, frames_fps=self.settings.pipeline_frames_fps,
        )  # fmt: skip
        progress.set("analyze", "Анализ видео", ANALYZE_SPAN[0], force=True)
        t0 = time.monotonic()
        try:
            output = analyzer.run(
                str(files.normalized), ctx, timeout_sec=ctx.time_budget_sec,
                on_progress=lambda pct, text: progress.set("analyze", text or "Анализ видео",
                                                           _scale(ANALYZE_SPAN, pct / 100)),
                on_event=lambda _e: None,
            )  # fmt: skip
        except AnalyzerTimeout as exc:
            self._on_timeout(job_id, info, files, exc.partial_events, stage="analyze", deadline=deadline)
            return
        self._stage_done(job_id, "analyze", t0)
        self._finish(job_id, info, files, output, progress, deadline, partial=False)

    def _finish(
        self, job_id: str, info: VideoInfo, files: JobFiles, output: AnalyzerOutput,
        progress: _Progress, deadline: _Deadline, *, partial: bool,
    ) -> None:  # fmt: skip
        progress.set("evidence", EVIDENCE_TEXT, EVIDENCE_SPAN[0], force=True)
        t0 = time.monotonic()
        events = self._select_events(job_id, output.events)
        if partial and not events:
            # e.g. every partial event was dropped by REVIEW_POLICY: never report a clean result
            self._fail(job_id, "timeout", "timeout")
            return
        pngs = self._extract_video_frames(events, info, files, deadline)
        violations = []
        for i, event in enumerate(events):
            try:
                frames = self._frames_for(event, info, files, pngs)
            except MediaError:
                log.warning("violation_without_evidence_skipped", extra={"job_id": job_id, "index": i})
                continue
            violations.append(stored_violation(self._clamped(event, info), self.catalog, frames))
            progress.set("evidence", EVIDENCE_TEXT, _scale(EVIDENCE_SPAN, (i + 1) / len(events)))
        if events and not violations:
            # Every event lost its frames: reporting no_violation would hide them, so fail.
            raise MediaError("no_evidence", "No evidence frame could be produced")
        debug = {**output.debug, "events_raw": len(output.events)}
        result = stored_result(violations, partial=partial, debug=debug)
        self.store.update(job_id, status=DONE, stage="done", stage_text="Готово", progress=100,
                          result=result, finished_at=time.time())  # fmt: skip
        self._stage_done(job_id, "evidence", t0)

    # -- helpers ----------------------------------------------------------------------------

    def _select_events(self, job_id: str, raw: tuple[DetectedEvent, ...]) -> list[DetectedEvent]:
        events = sorted(apply_review_policy(raw, self.settings.review_policy), key=lambda e: e.timecode_sec)
        cap = self.settings.max_violations
        if len(events) > cap:
            log.warning("violations_truncated", extra={"job_id": job_id, "reported": len(events), "kept": cap})
        return events[:cap]

    def _last_ts(self, info: VideoInfo) -> float:
        last = evidence.clamp_timestamp(info.duration_sec, info.duration_sec, info.fps)
        return math.floor(last * 10) / 10

    def _safe_ts(self, t: float, info: VideoInfo) -> float:
        return min(max(0.0, round1(t)), self._last_ts(info))

    def _clamped(self, event: DetectedEvent, info: VideoInfo) -> DetectedEvent:
        return replace(event, timecode_sec=self._safe_ts(event.timecode_sec, info))

    def _resolve_analyzer_image(self, files: JobFiles, image_path: str) -> Path:
        path = Path(image_path).resolve()
        if not path.is_relative_to(files.work_dir.resolve()):
            raise MediaError("frame_read_failed", "Analyzer frame outside the job work dir")
        return path

    def _refs(self, event: DetectedEvent) -> tuple[EvidenceRef, ...]:
        return event.evidence[:3] or (EvidenceRef(timestamp_sec=event.timecode_sec),)

    def _extract_video_frames(
        self, events: list[DetectedEvent], info: VideoInfo, files: JobFiles, deadline: _Deadline
    ) -> dict[float, tuple[float, bytes]]:
        """wanted timestamp -> (actual timestamp, PNG). A frame that fails to decode is retried
        RETRY_OFFSET_SEC earlier; the frame then reports that earlier, real timestamp."""
        wanted = sorted({self._safe_ts(r.timestamp_sec, info) for e in events for r in self._refs(e)
                         if not r.image_path})  # fmt: skip
        if not wanted:
            return {}
        out_dir = files.root / "evidence"
        # Keep a little time for JSON + DB write, but never more than a quarter of the reserve.
        until = deadline.monotonic - min(FINALIZE_MARGIN_SEC, self.settings.evidence_reserve_sec / 4)
        first = evidence.extract_frames_png(self.settings.ffmpeg_bin, files.normalized, wanted, out_dir,
                                            deadline=until)  # fmt: skip
        pngs = {t: (t, png) for t, png in first.items()}
        missing: dict[float, list[float]] = {}
        for t in wanted:
            if t not in pngs:
                missing.setdefault(round1(max(0.0, t - RETRY_OFFSET_SEC)), []).append(t)
        if missing:
            retried = evidence.extract_frames_png(self.settings.ffmpeg_bin, files.normalized, list(missing),
                                                  out_dir, deadline=until)  # fmt: skip
            for retry_t, png in retried.items():
                for original in missing[retry_t]:
                    pngs[original] = (retry_t, png)
            log.warning("evidence_frames_retried", extra={"count": sum(map(len, missing.values())),
                                                          "recovered": len(retried)})  # fmt: skip
        return pngs

    def _frames_for(
        self, event: DetectedEvent, info: VideoInfo, files: JobFiles, pngs: dict[float, tuple[float, bytes]]
    ) -> list[dict[str, Any]]:
        s = self.settings
        opts = {"max_side": s.evidence_max_side, "quality": s.evidence_jpeg_quality, "max_bytes": s.evidence_max_bytes}
        frames: list[dict[str, Any]] = []
        seen: set[float] = set()
        for ref in self._refs(event):
            wanted = self._safe_ts(ref.timestamp_sec, info)
            try:
                if ref.image_path:
                    t = wanted
                    jpeg = evidence.jpeg_from_file(self._resolve_analyzer_image(files, ref.image_path), **opts)
                elif wanted in pngs:
                    t, png = pngs[wanted]
                    jpeg = evidence.jpeg_from_png(png, **opts)
                else:
                    raise MediaError("frame_extract_failed", "Evidence frame could not be extracted")
            except MediaError as exc:
                log.warning("evidence_frame_skipped", extra={"code": exc.code, "timestamp_sec": wanted})
                continue
            if t in seen:
                continue
            seen.add(t)
            frames.append({"timestamp_sec": t, "jpeg_base64": evidence.to_base64(jpeg)})
        if not frames:
            # Dropping the event could silently flip the verdict to no_violation: fail instead.
            raise MediaError("no_evidence", "No evidence frame could be produced")
        return frames

    def _on_timeout(
        self, job_id: str, info: VideoInfo, files: JobFiles, partial: tuple[DetectedEvent, ...], *,
        stage: str, deadline: _Deadline | None = None,
    ) -> None:  # fmt: skip
        log.warning("job_timeout", extra={"job_id": job_id, "stage": stage, "partial_events": len(partial),
                                          "fallback": self.settings.timeout_fallback.value})  # fmt: skip
        # Partial results only make sense if analysis really ran and found something; an empty
        # partial result must never read as no_violation.
        use_partial = (self.settings.timeout_fallback is TimeoutFallback.PARTIAL and stage == "analyze"
                       and partial and deadline is not None and files.normalized.exists())  # fmt: skip
        if use_partial:
            output = AnalyzerOutput(events=partial, debug={"timeout_stage": stage})
            self._finish(job_id, info, files, output, _Progress(self.store, job_id), deadline, partial=True)
            return
        self._fail(job_id, "timeout", "timeout")

    def _fail(self, job_id: str, code: str, message: str) -> None:
        self.store.update(job_id, status=FAILED, stage="failed", stage_text="Ошибка", error=message,
                          error_code=code, finished_at=time.time())  # fmt: skip

    def _stage_done(self, job_id: str, stage: str, t0: float) -> None:
        log.info("job_stage_done", extra={"job_id": job_id, "stage": stage,
                                          "duration_sec": round(time.monotonic() - t0, 2)})  # fmt: skip

    def _log_finished(self, job_id: str) -> None:
        rec = self.store.get(job_id)
        if rec is None:
            return
        n = len((rec.result or {}).get("violations", []))
        log.info("job_finished", extra={
            "job_id": job_id, "status": rec.status, "error_code": rec.error_code, "violations": n,
            "queue_wait_sec": _r(rec.queue_wait_sec), "processing_sec": _r(rec.processing_sec),
            "total_sec": _r(rec.total_sec),
        })  # fmt: skip


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 2)
