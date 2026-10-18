"""Turns analyzer output into the stored result, and stored jobs into public / UI responses."""

from __future__ import annotations

from typing import Any

from app.analysis.legal import LegalCatalog
from app.analysis.port import DetectedEvent
from app.config import ReviewPolicy
from app.jobs.store import DONE, FAILED, QUEUED, JobRecord
from app.schemas.public import EvidenceFrame, JobDone, JobFailed, JobProcessing, PublicJob, Violation
from app.schemas.ui import LegalRefOut, UiFrame, UiJob, UiTimings, UiVideo, UiViolation

MAX_FRAMES = 3
UNKNOWN_TYPE = "Неклассифицированное событие"
FALLBACK_DESCRIPTION = "Обнаружен момент, похожий на нарушение"


def round1(value: float) -> float:
    return round(float(value), 1)


def apply_review_policy(events: tuple[DetectedEvent, ...], policy: ReviewPolicy) -> list[DetectedEvent]:
    if policy is ReviewPolicy.DROP:
        return [e for e in events if not e.needs_review]
    return list(events)


def stored_violation(event: DetectedEvent, catalog: LegalCatalog, frames: list[dict[str, Any]]) -> dict[str, Any]:
    if catalog.is_observation_only(event.type_code):
        raise ValueError("Observation-only candidate cannot be returned as a violation")
    ref = catalog.legal_ref(event.type_code, event.rule_id)
    type_name = catalog.type_name(event.type_code, event.type_name).strip() or UNKNOWN_TYPE
    return {
        "type": type_name,
        "type_code": event.type_code,
        "timecode_sec": round1(event.timecode_sec),
        # The public contract requires a non-empty description.
        "description": (event.description or "").strip() or f"{FALLBACK_DESCRIPTION}: {type_name}.",
        "legal_ref": None if ref is None else {
            "document": ref.document, "punkt": ref.punkt, "rule_text": ref.rule_text, "url": ref.url,
            "citation": ref.citation(),
        },
        "needs_review": event.needs_review,
        "frames": frames[:MAX_FRAMES],
    }  # fmt: skip


def stored_result(violations: list[dict[str, Any]], *, partial: bool, debug: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict": "violation" if violations else "no_violation",
        "partial": partial,
        "violations": violations,
        "debug": debug,
    }


def _public_description(v: dict[str, Any]) -> str:
    ref = v.get("legal_ref")
    return f"{v['description']} {ref['citation']}" if ref else v["description"]


def public_view(rec: JobRecord) -> PublicJob:
    if rec.status == FAILED:
        return JobFailed(job_id=rec.id, error=rec.error or "processing failed")
    if rec.status != DONE or rec.result is None:
        return JobProcessing(job_id=rec.id)
    violations = [
        Violation(
            type=v["type"],
            timecode_sec=v["timecode_sec"],
            description=_public_description(v),
            evidence_frames=[EvidenceFrame(timestamp_sec=f["timestamp_sec"], image_base64=f["jpeg_base64"])
                             for f in v["frames"]],  # fmt: skip
        )
        for v in rec.result["violations"]
    ]
    return JobDone(job_id=rec.id, verdict="violation" if violations else "no_violation", violations=violations)


def ui_view(rec: JobRecord, *, queue_position: int | None, preview_available: bool) -> UiJob:
    base = f"/ui/jobs/{rec.id}"
    meta = rec.video_meta or {}
    width, height = meta.get("display_width"), meta.get("display_height")
    result = rec.result or {}
    violations = [
        UiViolation(
            type=v["type"],
            type_code=v["type_code"],
            timecode_sec=v["timecode_sec"],
            description=v["description"],
            legal_ref=LegalRefOut(**{k: v["legal_ref"][k] for k in ("document", "punkt", "rule_text", "url")})
            if v.get("legal_ref") else None,
            needs_review=v.get("needs_review", False),
            evidence_frames=[UiFrame(timestamp_sec=f["timestamp_sec"], url=f"{base}/frames/{vi}/{fi}.jpg")
                             for fi, f in enumerate(v["frames"])],
        )
        for vi, v in enumerate(result.get("violations", []))
    ]  # fmt: skip
    return UiJob(
        job_id=rec.id,
        status=rec.status,  # type: ignore[arg-type]
        stage=rec.stage,
        stage_text=rec.stage_text,
        progress=100 if rec.status == DONE else rec.progress,
        queue_position=queue_position if rec.status == QUEUED else None,
        error=rec.error,
        error_code=rec.error_code,
        timings=UiTimings(queue_wait_sec=rec.queue_wait_sec, processing_sec=rec.processing_sec,
                          total_sec=rec.total_sec),  # fmt: skip
        video=UiVideo(
            duration_sec=meta.get("duration_sec"), fps=meta.get("fps"), width=width, height=height,
            preview_url=f"{base}/preview.mp4" if preview_available else None,
        ),
        verdict=result.get("verdict") if rec.status == DONE else None,
        partial=bool(result.get("partial", False)),
        violations=violations,
        result_url=f"{base}/result.json" if rec.status == DONE else None,
    )
