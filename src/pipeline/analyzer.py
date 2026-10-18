"""Real analyzer (PIPELINE=real): RF-DETR detector + rule engine (src/pipeline/rules.py).

The backend imports create_analyzer once in a dedicated child process, so the model loads once
and the process can be killed at the deadline. Weights come from DETECTOR_WEIGHTS (default
/models/detector/checkpoint_best_total.pth) and are read locally: no network access.
"""

from __future__ import annotations

import os

from app.analysis.port import AnalyzerOutput, DetectedEvent, EvidenceRef, JobContext, Reporter
from pipeline import rules

DEFAULT_WEIGHTS = "/models/detector/checkpoint_best_total.pth"


class RealAnalyzer:
    def __init__(self) -> None:
        from pipeline.detector import Detector

        self.detector = Detector(
            os.environ.get("DETECTOR_WEIGHTS", DEFAULT_WEIGHTS),
            threshold=float(os.environ.get("DETECTOR_THRESHOLD", "0.35")),
            fps=float(os.environ.get("DETECTOR_FPS", "5")),
        )

    def analyze_video(self, video_path: str, ctx: JobContext, reporter: Reporter) -> AnalyzerOutput:
        reporter.progress(0, "Поиск людей и предметов")
        doc = self.detector.run(video_path, on_progress=lambda p: reporter.progress(int(85 * p), "Поиск людей и предметов"))
        reporter.progress(90, "Проверка правил")
        result = rules.evaluate(doc)
        events = []
        for v in result.violations:
            ev = DetectedEvent(
                type_code=v.code,
                timecode_sec=v.t,
                description=v.description,
                evidence=tuple(EvidenceRef(timestamp_sec=t) for t in v.evidence[:3]),
                rule_id=v.rule_id,  # the catalogue resolves it to the legal text (rules.CATALOGUE)
                needs_review=v.needs_review,
            )
            reporter.event(ev)
            events.append(ev)
        reporter.progress(100, "Готово")
        debug = dict(result.debug, frames=len(doc["frames"]), timing=doc.get("timing"))
        return AnalyzerOutput(events=tuple(events), debug=debug)


def create_analyzer() -> RealAnalyzer:
    return RealAnalyzer()
